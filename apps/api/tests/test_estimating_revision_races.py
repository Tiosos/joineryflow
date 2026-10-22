"""Regression cases from the consolidated main review."""
from decimal import Decimal
import pytest
from sqlalchemy import text
from app.db import SessionLocal
from app.estimating import queries as estimates
from .helpers_concurrency import finish_after_waiting
from .helpers_estimating import _bootstrap, _make_estimate
from .helpers_material_take import _sql

pytestmark = pytest.mark.usefixtures('truncate_after')


def _quote():
    client, wid, uid, *_ = _bootstrap()
    rid = _make_estimate(client)['current_revision_id']
    lids = []
    for label in ['A', 'B']:
        r = client.post(f'/revisions/{rid}/lines', json={'description': label, 'qty': '1'})
        assert r.status_code == 201, r.text
        lid = r.json()['line_id']
        assert client.patch(f'/lines/{lid}', json={'unit_sell_override': '100'}).status_code == 200
        lids.append(lid)
    return client, wid, uid, rid, lids


def test_r02_parallel_quote_edits_keep_totals_consistent():
    _, wid, uid, rid, lids = _quote()
    with SessionLocal() as first:
        estimates.patch_line(first, line_id=lids[0], workspace_id=wid, actor_id=uid,
                             fields={'unit_sell_override': Decimal(200)}, clear_unit_sell_override=False)
        finish_after_waiting(first, lambda second: estimates.patch_line(second, line_id=lids[1],
            workspace_id=wid, actor_id=uid, fields={'unit_sell_override': Decimal(200)}, clear_unit_sell_override=False))
    assert _sql('SELECT subtotal_sell FROM estimate_revision WHERE revision_id=:r', r=rid) == 400
    assert _sql('SELECT total_inc_gst FROM estimate_revision WHERE revision_id=:r', r=rid) == 440


def test_r03_submission_wins_over_an_inflight_line_edit():
    _, wid, uid, rid, lids = _quote()
    _sql("UPDATE estimate_revision SET status='MGMT_APPROVAL' WHERE revision_id=:r", r=rid)
    with SessionLocal() as first:
        estimates.transition_revision(first, revision_id=rid, workspace_id=wid, actor_id=uid, target='SUBMITTED')
        with pytest.raises(ValueError, match='REVISION_LOCKED'):
            finish_after_waiting(first, lambda second: estimates.patch_line(second, line_id=lids[0],
                workspace_id=wid, actor_id=uid, fields={'description': 'Changed'}, clear_unit_sell_override=False))
    assert _sql('SELECT description FROM estimate_line WHERE line_id=:l', l=lids[0]) == 'A'


@pytest.mark.parametrize('operation', [
    'line_delete', 'line_reorder', 'part_add', 'part_patch', 'part_remove',
    'hardware_add', 'hardware_patch', 'hardware_remove', 'labour', 'markup', 'terms',
])
def test_submission_blocks_every_quote_mutation_after_lock_wait(operation):
    _, wid, uid, rid, lids = _quote()
    board = _sql('SELECT material_id FROM board_materials WHERE workspace_id=:w', w=wid)
    hardware = _sql('SELECT material_id FROM hardware_materials WHERE workspace_id=:w', w=wid)
    part_payload = {'material_type': 'BOARD', 'material_id': board, 'qty': Decimal(1)}
    hardware_payload = {'material_type': 'HARDWARE', 'material_id': hardware, 'qty': Decimal(1)}
    with SessionLocal() as setup:
        part_id = estimates.add_part(setup, line_id=lids[0], workspace_id=wid, actor_id=uid, payload=part_payload)
        hw_id = estimates.add_hardware(setup, line_id=lids[0], workspace_id=wid, actor_id=uid, payload=hardware_payload)
        setup.execute(text("UPDATE estimate_revision SET status='MGMT_APPROVAL' WHERE revision_id=:r"), {'r': rid})
        setup.commit()

    def mutate(second):
        common = {'workspace_id': wid, 'actor_id': uid}
        if operation == 'line_delete':
            return estimates.delete_line(second, line_id=lids[0], **common)
        if operation == 'line_reorder':
            return estimates.reorder_lines(second, revision_id=rid, ordered_line_ids=list(reversed(lids)), **common)
        if operation == 'part_add':
            return estimates.add_part(second, line_id=lids[0], payload=part_payload, **common)
        if operation == 'part_patch':
            return estimates.patch_part(second, part_id=part_id, fields={'qty': Decimal(2)}, **common)
        if operation == 'part_remove':
            return estimates.remove_part(second, part_id=part_id, **common)
        if operation == 'hardware_add':
            return estimates.add_hardware(second, line_id=lids[0], payload=hardware_payload, **common)
        if operation == 'hardware_patch':
            return estimates.patch_hardware(second, hw_id=hw_id, fields={'qty': Decimal(2)}, **common)
        if operation == 'hardware_remove':
            return estimates.remove_hardware(second, hw_id=hw_id, **common)
        if operation == 'labour':
            return estimates.upsert_labour(second, line_id=lids[0], stage_key='CNC', hours=Decimal(1), **common)
        fields = {'markup_pct': Decimal(25)} if operation == 'markup' else {'terms_text': 'Late terms'}
        return estimates.patch_revision(second, revision_id=rid, fields=fields, **common)

    with SessionLocal() as first:
        estimates.transition_revision(first, revision_id=rid, workspace_id=wid, actor_id=uid, target='SUBMITTED')
        with pytest.raises(ValueError, match='REVISION_LOCKED'):
            finish_after_waiting(first, mutate)
