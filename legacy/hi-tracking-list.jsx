// Hi-fi: Tracking + List (Cutlist + Hardware Portal unified)
// Tracking: table+drawer pattern, all filters pills
// List: subtabs — Cutlist | Hardware Portal
//   Cutlist default view combines legacy dense table with room-tree sidebar and CV-import modal affordance
//   Hardware Portal: dual-pane cart + pantry with catalogue grouping within the cart

// ───────── TRACKING ─────────
const HiTracking = () => {
  const rows = [
    ['L3-R01-P01', 'Reception desk carcass', 'L3 · Reception', 'Carcass', 'CLEAR', 'Ordered 18/04', 'JR'],
    ['L3-R01-P02', 'Reception desk front panels', 'L3 · Reception', 'Front', 'APPROVED', 'QA by SO', 'SO'],
    ['L3-R01-P03', 'Reception shelf A (veneer)', 'L3 · Reception', 'Shelf', 'LIVE', 'In production', 'TA'],
    ['L3-R01-P04', 'Reception end-panel (oak veneer)', 'L3 · Reception', 'Panel', 'HOLD', 'Waiting: A-23', 'BM'],
    ['L3-R02-P11', 'Meeting room island', 'L3 · Meeting Rm', 'Island', 'NOTE!', 'See note from JR', 'JR'],
    ['L3-R02-P12', 'Meeting room cabinets', 'L3 · Meeting Rm', 'Cab', 'SUBMITTED', 'Shop dwg v2', 'RP'],
    ['L3-R02-P13', 'Meeting room door 01', 'L3 · Meeting Rm', 'Door', 'REJECTED', 'See note v1', 'JR'],
    ['L3-R02-P14', 'Meeting room door 02', 'L3 · Meeting Rm', 'Door', 'VOID', 'Superseded', '—'],
    ['L3-R02-P15', 'Meeting room counter', 'L3 · Meeting Rm', 'Counter', 'RTO', 'Return → Polytec', 'MK'],
    ['L3-R03-P21', 'Staff kitchen — upper cabs', 'L3 · Staff Kitchen', 'Cab', 'CLEAR', '—', 'JR'],
    ['L3-R03-P22', 'Staff kitchen — lower cabs', 'L3 · Staff Kitchen', 'Cab', 'CLEAR', '—', 'JR'],
    ['L3-R03-P23', 'Staff kitchen — island counter', 'L3 · Staff Kitchen', 'Counter', 'LIVE', 'CNC cut', 'SO'],
    ['L3-R04-P31', 'Breakout booth L (assembled)', 'L3 · Breakout', 'Assembly', 'APPROVED', 'Ready to ship', 'JR'],
    ['L3-R04-P32', 'Breakout booth R (assembled)', 'L3 · Breakout', 'Assembly', 'APPROVED', 'Ready to ship', 'JR'],
  ];
  const userColors = { JR: '#3d6b8a', SO: '#7a5193', TA: '#6f7a51', BM: H.accent, RP: '#3f7d48', MK: '#b4443d' };
  const statusTally = [
    ['All', 14, null],
    ['CLEAR', 3, H.good],
    ['APPROVED', 3, H.good],
    ['LIVE', 2, H.accent],
    ['HOLD', 1, H.warn],
    ['NOTE!', 1, H.warn],
    ['SUBMITTED', 1, H.info],
    ['REJECTED', 1, H.bad],
    ['VOID', 1, H.bad],
    ['RTO', 1, H.accent],
  ];
  return (
    <HAppChrome active="Tracking">
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <HiPageHeader
          title="Tracking · Alfred L3"
          sub="Part-level status across all rooms. 237 parts, 14 statuses tracked."
          right={<>
            <button className="h-btn"><HIcon d={Icons.download} size={11}/> Export</button>
            <button className="h-btn" style={{ marginLeft: 6 }}><HIcon d={Icons.print} size={11}/> Print manifest</button>
            <button className="h-btn h-btn-accent" style={{ marginLeft: 6 }}><HIcon d={Icons.plus} size={11}/> Add part</button>
          </>}
        />

        {/* status tally row */}
        <div style={{ padding: '0 20px 10px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {statusTally.map(([s, n, c], i) => (
            <div key={s} style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px',
              borderRadius: 14, fontSize: 11.5, fontWeight: 500, cursor: 'pointer',
              background: i === 0 ? H.ink : H.surface, color: i === 0 ? H.bg : H.ink,
              border: `1px solid ${i === 0 ? H.ink : H.line}`,
            }}>
              {c && <span style={{ width: 6, height: 6, borderRadius: '50%', background: c }}/>}
              <span>{s}</span>
              <span className="h-mono" style={{ color: i === 0 ? H.ink4 : H.ink3, fontSize: 10.5 }}>{n}</span>
            </div>
          ))}
        </div>

        <div style={{ flex: 1, display: 'flex', minHeight: 0, padding: '0 20px 20px', gap: 14 }}>
          {/* table */}
          <div className="h-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderBottom: `1px solid ${H.line}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 8px', background: H.bg, border: `1px solid ${H.line}`, borderRadius: 5, flex: '0 0 220px' }}>
                <HIcon d={Icons.search} size={11} stroke={H.ink3}/>
                <span style={{ fontSize: 11.5, color: H.ink3 }}>Search parts…</span>
              </div>
              <button className="h-btn">Room: All <HIcon d={Icons.chev} size={9}/></button>
              <button className="h-btn">Type: All <HIcon d={Icons.chev} size={9}/></button>
              <button className="h-btn">Assignee: All <HIcon d={Icons.chev} size={9}/></button>
              <div style={{ flex: 1 }}/>
              <span style={{ fontSize: 11, color: H.ink3 }}>14 of 237</span>
              <button className="h-btn h-btn-ghost" style={{ padding: 4 }}><HIcon d={Icons.grid} size={12}/></button>
              <button className="h-btn h-btn-ghost" style={{ padding: 4, background: H.surfaceAlt }}><HIcon d={Icons.list} size={12}/></button>
            </div>

            <div style={{ flex: 1, overflow: 'auto' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '110px 2fr 1.1fr 0.7fr 90px 1.1fr 40px', gap: 10, padding: '8px 14px', background: H.surfaceAlt, fontSize: 10, fontWeight: 600, color: H.ink3, letterSpacing: 0.06, textTransform: 'uppercase', borderBottom: `1px solid ${H.line}`, position: 'sticky', top: 0 }}>
                <span>Part #</span><span>Description</span><span>Location</span><span>Type</span><span>Status</span><span>Note</span><span></span>
              </div>
              {rows.map((r, i) => (
                <div key={i} className="h-row-hover" style={{ display: 'grid', gridTemplateColumns: '110px 2fr 1.1fr 0.7fr 90px 1.1fr 40px', gap: 10, padding: '9px 14px', borderBottom: `1px solid ${H.line}`, fontSize: 12, alignItems: 'center', background: i === 4 ? H.accentSoft + '66' : 'transparent' }}>
                  <span className="h-mono" style={{ color: H.ink2, fontSize: 11 }}>{r[0]}</span>
                  <span style={{ fontWeight: i === 4 ? 600 : 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r[1]}</span>
                  <span style={{ color: H.ink2, fontSize: 11.5 }}>{r[2]}</span>
                  <span style={{ color: H.ink2, fontSize: 11.5 }}>{r[3]}</span>
                  <span><HStatus s={r[4]}/></span>
                  <span style={{ color: H.ink3, fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r[5]}</span>
                  <span style={{ textAlign: 'right' }}>
                    {r[6] !== '—' ? <HAvatar label={r[6]} color={userColors[r[6]]} size={22}/> : <span style={{ color: H.ink4 }}>—</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* drawer — selected part */}
          <div className="h-card" style={{ width: 320, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
            <div style={{ padding: '12px 14px', borderBottom: `1px solid ${H.line}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <HStatus s="NOTE!"/>
                <span className="h-mono" style={{ fontSize: 10.5, color: H.ink3 }}>L3-R02-P11</span>
                <div style={{ flex: 1 }}/>
                <HIcon d={Icons.x} size={12} stroke={H.ink3}/>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, letterSpacing: -0.2 }}>Meeting room island</div>
              <div style={{ fontSize: 11.5, color: H.ink2, marginTop: 2 }}>L3 · Meeting Rm · Island carcass</div>
            </div>
            <div style={{ padding: 14, overflow: 'auto', flex: 1 }}>
              <div className="h-eyebrow" style={{ marginBottom: 6 }}>Specs</div>
              <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', fontSize: 11.5, rowGap: 4 }}>
                <span style={{ color: H.ink3 }}>Material</span><span>Oak veneer / 18mm MR MDF</span>
                <span style={{ color: H.ink3 }}>Dimensions</span><span className="h-mono">2450 × 900 × 900 mm</span>
                <span style={{ color: H.ink3 }}>Edging</span><span>3mm matching oak</span>
                <span style={{ color: H.ink3 }}>Hardware</span><span>Blum · 110° soft-close ×8</span>
              </div>

              <div className="h-eyebrow" style={{ marginTop: 14, marginBottom: 6 }}>Note from Jules</div>
              <div style={{ fontSize: 11.5, background: H.warnSoft, borderLeft: `3px solid ${H.warn}`, padding: '8px 10px', borderRadius: 3, color: H.ink }}>
                Waiting on veneer confirmation from Briggs. Do not release to CNC until sample A-23 is signed off by client.
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                <button className="h-btn h-btn-accent" style={{ flex: 1, justifyContent: 'center' }}>Set status</button>
                <button className="h-btn" style={{ flex: 1, justifyContent: 'center' }}>Reply</button>
              </div>

              <div className="h-eyebrow" style={{ marginTop: 14, marginBottom: 6 }}>History</div>
              {[
                ['NOTE!', 'Jules Roh', 'Waiting on veneer confirmation', '18m'],
                ['SUBMITTED', 'Rin Park', 'Shop dwg v2 uploaded', '2h'],
                ['CLEAR', 'Bill Ma', 'Specs locked', '2d'],
                ['—', 'Bill Ma', 'Created from cutlist import', '5d'],
              ].map((e, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, padding: '6px 0', borderBottom: i < 3 ? `1px dashed ${H.line}` : 'none', fontSize: 11.5 }}>
                  {e[0] !== '—' ? <HStatus s={e[0]}/> : <span className="h-pill">start</span>}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div><b style={{ fontWeight: 600 }}>{e[1]}</b> <span style={{ color: H.ink2 }}>· {e[2]}</span></div>
                  </div>
                  <span className="h-mono" style={{ fontSize: 10.5, color: H.ink3 }}>{e[3]}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </HAppChrome>
  );
};

// ───────── LIST — CUTLIST subtab (DEFAULT) ─────────
const HiListCutlist = () => {
  const rooms = [
    ['Reception', 12, true],
    ['Meeting Rm', 18, false],
    ['Staff Kitchen', 24, false],
    ['Breakout', 16, false],
    ['Print Room', 6, false],
    ['Corridor A', 9, false],
    ['Corridor B', 9, false],
  ];
  const parts = [
    ['R01.P01', 'Reception desk carcass', '2450×900×900', '18mm MR MDF', 'Oak v.', '3mm oak', 4, 'CLEAR'],
    ['R01.P02', 'Reception front panel', '2450×300×18', '18mm MR MDF', 'Oak v.', '3mm oak', 2, 'APPROVED'],
    ['R01.P03', 'Reception shelf A', '1800×350×18', '18mm MR MDF', 'White lam', '1mm white', 3, 'LIVE'],
    ['R01.P04', 'Reception shelf B', '1800×350×18', '18mm MR MDF', 'White lam', '1mm white', 3, 'LIVE'],
    ['R01.P05', 'Reception end panel L', '900×600×18', '18mm MR MDF', 'Oak v.', '3mm oak', 1, 'HOLD'],
    ['R01.P06', 'Reception end panel R', '900×600×18', '18mm MR MDF', 'Oak v.', '3mm oak', 1, 'HOLD'],
    ['R01.P07', 'Reception toe-kick', '2450×100×18', '18mm MDF', 'Black', '—', 2, 'CLEAR'],
    ['R01.P08', 'Reception cable tray', '2450×120×18', '18mm MDF', '—', '—', 2, 'CLEAR'],
    ['R01.P09', 'Reception counter L', '1300×650×38', '38mm Corian', '—', '—', 1, 'SUBMITTED'],
    ['R01.P10', 'Reception counter R', '1300×650×38', '38mm Corian', '—', '—', 1, 'SUBMITTED'],
    ['R01.P11', 'Reception divider', '1200×900×18', '18mm MR MDF', 'Oak v.', '3mm oak', 1, 'NOTE!'],
    ['R01.P12', 'Reception kickplate', '2450×80×3', '3mm s/steel', '—', '—', 1, 'ORDERED'],
  ];
  const sub = [
    { key: 'cutlist', label: 'Cutlist', count: 94 },
    { key: 'hardware', label: 'Hardware Portal', count: 58 },
  ];
  return (
    <HAppChrome active="List" subtabs={sub} activeSub="cutlist" chromeExtra={
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '0 0 0 8px' }}>
        <button className="h-btn"><HIcon d={Icons.import} size={11}/> Import CV</button>
        <button className="h-btn h-btn-accent"><HIcon d={Icons.plus} size={11}/> Add part</button>
      </div>
    }>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <HiPageHeader
          title="Cutlist · Alfred L3"
          sub="94 parts across 7 rooms. Version: rev-C (20 Apr) · Linked to Tracking."
          right={<>
            <span className="h-pill">Rev C</span>
            <button className="h-btn" style={{ marginLeft: 6 }}><HIcon d={Icons.history} size={11}/> History</button>
            <button className="h-btn"><HIcon d={Icons.download} size={11}/> Export</button>
          </>}
        />

        <div style={{ flex: 1, display: 'flex', minHeight: 0, padding: '0 20px 20px', gap: 14 }}>
          {/* room tree (B direction baked in) */}
          <div className="h-card" style={{ width: 220, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
            <div style={{ padding: '11px 13px', borderBottom: `1px solid ${H.line}`, display: 'flex', alignItems: 'center', gap: 8 }}>
              <HIcon d={Icons.room} size={13} stroke={H.ink2}/>
              <div style={{ fontSize: 12.5, fontWeight: 600 }}>Rooms</div>
              <div style={{ flex: 1 }}/>
              <span style={{ color: H.ink3, fontSize: 15, cursor: 'pointer' }}>+</span>
            </div>
            <div style={{ overflow: 'auto', padding: '4px 6px 10px', fontSize: 12 }}>
              <div style={{ padding: '5px 8px', color: H.ink3, fontSize: 10.5, fontWeight: 600, letterSpacing: 0.06, textTransform: 'uppercase' }}>Level 3</div>
              {rooms.map(([n, c, on]) => (
                <div key={n} style={{ padding: '6px 10px', borderRadius: 5, marginBottom: 1, background: on ? H.accentSoft : 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, borderLeft: on ? `2px solid ${H.accent}` : '2px solid transparent' }}>
                  <HIcon d={Icons.chevR} size={9} stroke={H.ink3}/>
                  <span style={{ flex: 1, fontWeight: on ? 600 : 500, color: on ? H.accent : H.ink }}>{n}</span>
                  <span className="h-mono" style={{ color: H.ink3, fontSize: 10.5 }}>{c}</span>
                </div>
              ))}
              <div style={{ padding: '5px 8px', color: H.ink3, fontSize: 10.5, fontWeight: 600, letterSpacing: 0.06, textTransform: 'uppercase', marginTop: 10 }}>Common</div>
              {[['Lobby', 3], ['Lifts', 2]].map(([n, c]) => (
                <div key={n} style={{ padding: '6px 10px', borderRadius: 5, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <HIcon d={Icons.chevR} size={9} stroke={H.ink3}/>
                  <span style={{ flex: 1 }}>{n}</span>
                  <span className="h-mono" style={{ color: H.ink3, fontSize: 10.5 }}>{c}</span>
                </div>
              ))}
            </div>
            <div style={{ padding: '8px 12px', borderTop: `1px solid ${H.line}`, display: 'flex', alignItems: 'center', gap: 6 }}>
              <HIcon d={Icons.upload} size={12} stroke={H.accent}/>
              <span style={{ fontSize: 11.5, color: H.accent, cursor: 'pointer' }}>Import from CV…</span>
            </div>
          </div>

          {/* parts table */}
          <div className="h-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderBottom: `1px solid ${H.line}` }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Reception</div>
              <span className="h-pill">12 parts</span>
              <span className="h-pill" style={{ background: H.accentSoft, color: H.accent, borderColor: H.accent + '33' }}>3 changed in rev C</span>
              <div style={{ flex: 1 }}/>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 8px', background: H.bg, border: `1px solid ${H.line}`, borderRadius: 5 }}>
                <HIcon d={Icons.search} size={11} stroke={H.ink3}/>
                <span style={{ fontSize: 11.5, color: H.ink3 }}>Search in room…</span>
              </div>
              <button className="h-btn"><HIcon d={Icons.filter} size={11}/> Filter</button>
            </div>

            <div style={{ flex: 1, overflow: 'auto' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '90px 2fr 110px 1.1fr 0.9fr 1fr 50px 90px', gap: 10, padding: '7px 14px', background: H.surfaceAlt, fontSize: 10, fontWeight: 600, color: H.ink3, letterSpacing: 0.06, textTransform: 'uppercase', borderBottom: `1px solid ${H.line}`, position: 'sticky', top: 0, zIndex: 1 }}>
                <span>Part</span><span>Description</span><span>W × D × T</span><span>Substrate</span><span>Face</span><span>Edge</span><span>Qty</span><span>Status</span>
              </div>
              {parts.map((p, i) => (
                <div key={i} className="h-row-hover" style={{ display: 'grid', gridTemplateColumns: '90px 2fr 110px 1.1fr 0.9fr 1fr 50px 90px', gap: 10, padding: '8px 14px', borderBottom: `1px solid ${H.line}`, fontSize: 12, alignItems: 'center', background: i === 10 ? H.warnSoft + '66' : (i === 8 || i === 9) ? H.infoSoft + '33' : 'transparent' }}>
                  <span className="h-mono" style={{ color: H.ink2, fontSize: 11 }}>{p[0]}</span>
                  <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p[1]}</span>
                  <span className="h-mono" style={{ color: H.ink2, fontSize: 11 }}>{p[2]}</span>
                  <span style={{ color: H.ink2, fontSize: 11.5 }}>{p[3]}</span>
                  <span style={{ color: H.ink2, fontSize: 11.5 }}>{p[4]}</span>
                  <span style={{ color: H.ink2, fontSize: 11.5 }}>{p[5]}</span>
                  <span className="h-mono" style={{ color: H.ink, fontWeight: 600 }}>{p[6]}</span>
                  <span><HStatus s={p[7]}/></span>
                </div>
              ))}
            </div>

            {/* CV import affordance (D baked) */}
            <div style={{ borderTop: `1px solid ${H.line}`, background: H.accentSoft, padding: '9px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
              <HIcon d={Icons.upload} size={12} stroke={H.accent}/>
              <span style={{ fontSize: 12, color: H.accent, fontWeight: 500 }}>CV import: review 14 unmatched materials from "Alfred_L3_rev_D.csv"</span>
              <div style={{ flex: 1 }}/>
              <button className="h-btn" style={{ background: H.surface }}>Dismiss</button>
              <button className="h-btn h-btn-accent">Open review</button>
            </div>
          </div>
        </div>
      </div>
    </HAppChrome>
  );
};

// ───────── LIST — HARDWARE PORTAL subtab ─────────
const HiListHardware = () => {
  const pantry = [
    { cat: 'Hinges', items: [
      ['Blum 110° soft-close · clip-on', '71B3550', 142, 'Blum'],
      ['Blum 155° corner', '79B9550', 48, 'Blum'],
      ['Hafele 110° std', '329.29.503', 96, 'Hafele'],
    ]},
    { cat: 'Handles', items: [
      ['Bullnose 160mm brushed brass', 'HND-BN-160B', 38, 'Hafele'],
      ['Flush D 96mm matte black', 'HND-FD-96MB', 120, 'Hafele'],
      ['Knurled knob 28mm antique', 'HND-KN-28A', 24, 'Joseph Giles'],
    ]},
    { cat: 'Runners', items: [
      ['Tandembox plus 500mm', 'T-550H', 32, 'Blum'],
      ['Ball-bearing 450mm soft-close', 'BB-450SC', 60, 'Hafele'],
    ]},
    { cat: 'Fasteners', items: [
      ['Confirmat 7×50', 'CF-750', 2100, 'Ovvo'],
      ['Wood screw 4×40 countersunk', 'WS-440', 3200, 'Ovvo'],
      ['Shelf pin 5mm nickel', 'SP-5N', 580, 'Hafele'],
    ]},
  ];
  const cart = [
    { cat: 'Blum', items: [
      ['Blum 110° soft-close · clip-on', '71B3550', 120, 4.80, 'Alfred L3 · Meeting Rm'],
      ['Blum 155° corner', '79B9550', 18, 6.20, 'Alfred L3 · Meeting Rm'],
      ['Tandembox plus 500mm', 'T-550H', 24, 38.50, 'Alfred L3 · Staff Kitchen'],
    ]},
    { cat: 'Hafele', items: [
      ['Flush D 96mm matte black', 'HND-FD-96MB', 44, 12.40, 'Alfred L3 · Reception'],
      ['Ball-bearing 450mm soft-close', 'BB-450SC', 36, 22.00, 'Alfred L3 · Staff Kitchen'],
    ]},
    { cat: 'Ovvo', items: [
      ['Confirmat 7×50', 'CF-750', 600, 0.18, 'Alfred L3 · all rooms'],
    ]},
  ];
  const cartTotal = cart.reduce((s, c) => s + c.items.reduce((t, i) => t + i[2] * i[3], 0), 0);
  const sub = [
    { key: 'cutlist', label: 'Cutlist', count: 94 },
    { key: 'hardware', label: 'Hardware Portal', count: 58 },
  ];
  return (
    <HAppChrome active="List" subtabs={sub} activeSub="hardware" chromeExtra={
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '0 0 0 8px' }}>
        <button className="h-btn"><HIcon d={Icons.print} size={11}/> Kit sheet</button>
        <button className="h-btn h-btn-accent"><HIcon d={Icons.cart} size={11}/> Send to shop (58)</button>
      </div>
    }>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <HiPageHeader
          title="Hardware Portal · Alfred L3"
          sub="Pull items from pantry → cart → send to shop floor. Totals by catalogue."
          right={<>
            <button className="h-btn"><HIcon d={Icons.history} size={11}/> Previous pulls</button>
          </>}
        />

        <div style={{ flex: 1, display: 'flex', minHeight: 0, padding: '0 20px 20px', gap: 14 }}>
          {/* pantry (left) */}
          <div className="h-card" style={{ flex: 1.2, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
            <div style={{ padding: '10px 14px', borderBottom: `1px solid ${H.line}`, display: 'flex', alignItems: 'center', gap: 8 }}>
              <HIcon d={Icons.box} stroke={H.ink2}/>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Pantry</div>
              <span className="h-pill">in stock</span>
              <div style={{ flex: 1 }}/>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 8px', background: H.bg, border: `1px solid ${H.line}`, borderRadius: 5 }}>
                <HIcon d={Icons.search} size={11} stroke={H.ink3}/>
                <span style={{ fontSize: 11.5, color: H.ink3 }}>Search SKU, catalogue…</span>
              </div>
            </div>

            <div style={{ overflow: 'auto', flex: 1 }}>
              {pantry.map(sec => (
                <div key={sec.cat}>
                  <div style={{ padding: '7px 14px', background: H.surfaceAlt, fontSize: 10.5, fontWeight: 600, letterSpacing: 0.08, textTransform: 'uppercase', color: H.ink2, borderBottom: `1px solid ${H.line}`, borderTop: `1px solid ${H.line}`, display: 'flex', alignItems: 'center', gap: 8 }}>
                    {sec.cat}
                    <span className="h-mono" style={{ color: H.ink3, fontSize: 10 }}>{sec.items.length}</span>
                  </div>
                  {sec.items.map((it, i) => (
                    <div key={i} className="h-row-hover" style={{ display: 'grid', gridTemplateColumns: '2fr 110px 80px 1fr 90px', gap: 10, padding: '8px 14px', borderBottom: `1px solid ${H.line}`, fontSize: 12, alignItems: 'center' }}>
                      <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it[0]}</span>
                      <span className="h-mono" style={{ color: H.ink3, fontSize: 11 }}>{it[1]}</span>
                      <span className="h-mono" style={{ color: it[2] < 100 ? H.warn : H.ink, fontWeight: 500 }}>{it[2]}</span>
                      <span style={{ color: H.ink2, fontSize: 11.5 }}>{it[3]}</span>
                      <button className="h-btn" style={{ justifyContent: 'center', padding: '3px 8px' }}><HIcon d={Icons.plus} size={10}/> Pull</button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {/* cart (right) — grouped by catalogue */}
          <div className="h-card" style={{ width: 420, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
            <div style={{ padding: '10px 14px', borderBottom: `1px solid ${H.line}`, display: 'flex', alignItems: 'center', gap: 8 }}>
              <HIcon d={Icons.cart} stroke={H.accent}/>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Cart — Alfred L3</div>
              <span className="h-pill" style={{ background: H.accentSoft, color: H.accent, borderColor: H.accent + '33' }}>58 items</span>
              <div style={{ flex: 1 }}/>
              <span style={{ color: H.ink3, fontSize: 11 }}>draft</span>
            </div>

            <div style={{ flex: 1, overflow: 'auto' }}>
              {cart.map((sec, si) => {
                const tot = sec.items.reduce((t, i) => t + i[2] * i[3], 0);
                return (
                  <div key={sec.cat}>
                    <div style={{ padding: '8px 14px', background: H.surfaceAlt, borderBottom: `1px solid ${H.line}`, display: 'flex', alignItems: 'center', gap: 8, borderTop: si > 0 ? `1px solid ${H.line}` : 'none' }}>
                      <div style={{ fontSize: 11.5, fontWeight: 600 }}>{sec.cat}</div>
                      <span className="h-mono" style={{ color: H.ink3, fontSize: 10.5 }}>{sec.items.length} line{sec.items.length !== 1 && 's'}</span>
                      <div style={{ flex: 1 }}/>
                      <span className="h-mono" style={{ fontSize: 11.5, fontWeight: 600 }}>${tot.toFixed(2)}</span>
                    </div>
                    {sec.items.map((it, i) => (
                      <div key={i} style={{ padding: '8px 14px', borderBottom: `1px solid ${H.line}` }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it[0]}</div>
                            <div className="h-mono" style={{ fontSize: 10.5, color: H.ink3 }}>{it[1]} · {it[4]}</div>
                          </div>
                          <div style={{ display: 'inline-flex', alignItems: 'center', border: `1px solid ${H.line}`, borderRadius: 5, overflow: 'hidden' }}>
                            <button style={{ border: 'none', background: H.surface, padding: '2px 7px', fontSize: 12, color: H.ink2, cursor: 'pointer' }}>−</button>
                            <span className="h-mono" style={{ padding: '2px 8px', fontSize: 11.5, borderLeft: `1px solid ${H.line}`, borderRight: `1px solid ${H.line}`, minWidth: 32, textAlign: 'center' }}>{it[2]}</span>
                            <button style={{ border: 'none', background: H.surface, padding: '2px 7px', fontSize: 12, color: H.ink2, cursor: 'pointer' }}>+</button>
                          </div>
                          <span className="h-mono" style={{ fontSize: 11.5, width: 60, textAlign: 'right', color: H.ink2 }}>${(it[2] * it[3]).toFixed(2)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>

            {/* footer totals */}
            <div style={{ borderTop: `1px solid ${H.line}`, padding: '10px 14px', background: H.surfaceAlt }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: H.ink2, marginBottom: 3 }}>
                <span>Subtotal</span><span className="h-mono">${cartTotal.toFixed(2)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: H.ink2, marginBottom: 3 }}>
                <span>Shop labour est.</span><span className="h-mono">~6.5 h</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginTop: 6, paddingTop: 6, borderTop: `1px solid ${H.line}` }}>
                <span style={{ fontWeight: 600 }}>Total</span><span className="h-mono" style={{ fontWeight: 600 }}>${cartTotal.toFixed(2)}</span>
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                <button className="h-btn" style={{ flex: 1, justifyContent: 'center' }}>Save draft</button>
                <button className="h-btn h-btn-accent" style={{ flex: 1.3, justifyContent: 'center' }}>Send to shop →</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </HAppChrome>
  );
};

Object.assign(window, { HiTracking, HiListCutlist, HiListHardware });
