// Hi-fi: Orderbook (A default + subpanels), Shop Drawings, iSample (Samplebook)

// ───────── ORDERBOOK ─────────
// Subtabs: Open | In transit | Delivered | Returns/RTO | Suppliers
// A default: Open (grouped by supplier, dense table)

const HiOrderbookOpen = () => {
  const groups = [
    ['Blum', 6, 'Next: Thu 23', [
      ['PO-2273-011', 'Alfred L3', 'Hinges 110° clip-on ×120', '18 Apr', '23 Apr', 'LIVE', 576.00],
      ['PO-2273-012', 'Alfred L3', 'Tandembox 500mm ×24', '18 Apr', '23 Apr', 'LIVE', 924.00],
      ['PO-2351-003', 'Monash FFT', 'Soft-close runners ×40', '17 Apr', '24 Apr', 'ORDERED', 480.00],
    ]],
    ['Hafele', 4, 'Overdue: 1', [
      ['PO-2289-003', 'Trentham', 'Bullnose handles 160mm ×38', '14 Apr', '19 Apr', 'OVERDUE', 950.00],
      ['PO-2347-004', 'VSBA', 'Shelf pins + flush handles', '18 Apr', '24 Apr', 'LIVE', 412.00],
    ]],
    ['Briggs Veneer', 3, 'Next: Fri 24', [
      ['PO-2273-007', 'Alfred L3', 'Oak veneer 3.2m² sheets', '15 Apr', '24 Apr', 'LIVE', 3210.00],
      ['PO-2273-008', 'Alfred L3', 'Walnut banding 3mm ×24m', '18 Apr', '25 Apr', 'ORDERED', 288.00],
    ]],
    ['Polytec', 3, 'Overdue: 1', [
      ['PO-2351-007', 'Monash FFT', 'Formica Grey 18mm ×6', '15 Apr', '22 Apr', 'OVERDUE', 684.00],
    ]],
    ['Laminex', 2, 'Next: Fri 24', [
      ['PO-2347-009', 'VSBA', 'Impressions White satin ×4', '19 Apr', '24 Apr', 'LIVE', 364.00],
    ]],
  ];
  const sub = [
    { key: 'open', label: 'Open', count: 18 },
    { key: 'transit', label: 'In transit', count: 7 },
    { key: 'delivered', label: 'Delivered', count: 42 },
    { key: 'returns', label: 'Returns · RTO', count: 2 },
    { key: 'suppliers', label: 'Suppliers' },
  ];
  return (
    <HAppChrome active="Orderbook" subtabs={sub} activeSub="open" chromeExtra={
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '0 0 0 8px' }}>
        <button className="h-btn"><HIcon d={Icons.download} size={11}/> Export</button>
        <button className="h-btn h-btn-accent"><HIcon d={Icons.plus} size={11}/> New PO</button>
      </div>
    }>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <HiPageHeader
          title="Orderbook"
          sub="18 open POs · $14,820 outstanding · 2 overdue."
        />

        <div style={{ padding: '0 20px 10px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="h-btn h-btn-primary">All projects</button>
          <button className="h-btn">Alfred L3 <span className="h-mono" style={{ color: H.ink3, marginLeft: 4 }}>7</span></button>
          <button className="h-btn">Monash FFT <span className="h-mono" style={{ color: H.ink3, marginLeft: 4 }}>4</span></button>
          <button className="h-btn">VSBA <span className="h-mono" style={{ color: H.ink3, marginLeft: 4 }}>3</span></button>
          <button className="h-btn">Trentham <span className="h-mono" style={{ color: H.ink3, marginLeft: 4 }}>2</span></button>
          <div style={{ flex: 1 }}/>
          <button className="h-btn"><HIcon d={Icons.filter} size={11}/> Overdue only</button>
          <button className="h-btn"><HIcon d={Icons.grid} size={11}/> Kanban</button>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: '0 20px 20px' }}>
          <div className="h-card" style={{ overflow: 'hidden' }}>
            {groups.map((g, gi) => (
              <div key={g[0]}>
                <div style={{ display: 'flex', alignItems: 'center', padding: '10px 14px', background: H.surfaceAlt, borderTop: gi > 0 ? `1px solid ${H.line}` : 'none', borderBottom: `1px solid ${H.line}`, gap: 10 }}>
                  <div style={{ width: 24, height: 24, borderRadius: 5, background: H.surface, border: `1px solid ${H.line}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: H.ink2 }}>{g[0][0]}</div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{g[0]}</div>
                  <span className="h-pill">{g[1]} POs</span>
                  <span style={{ fontSize: 11, color: g[2].startsWith('Overdue') ? H.bad : H.ink3 }}>{g[2]}</span>
                  <div style={{ flex: 1 }}/>
                  <span className="h-mono" style={{ fontSize: 12, color: H.ink2 }}>${g[3].reduce((t, r) => t + r[6], 0).toFixed(2)}</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '130px 1fr 2fr 90px 90px 90px 90px 36px', gap: 10, padding: '7px 14px', background: H.bg, fontSize: 10, fontWeight: 600, color: H.ink3, letterSpacing: 0.06, textTransform: 'uppercase', borderBottom: `1px solid ${H.line}` }}>
                  <span>PO #</span><span>Project</span><span>Description</span><span>Ordered</span><span>ETA</span><span>Status</span><span style={{ textAlign: 'right' }}>Total</span><span></span>
                </div>
                {g[3].map((r, i) => (
                  <div key={i} className="h-row-hover" style={{ display: 'grid', gridTemplateColumns: '130px 1fr 2fr 90px 90px 90px 90px 36px', gap: 10, padding: '9px 14px', borderBottom: `1px solid ${H.line}`, fontSize: 12, alignItems: 'center' }}>
                    <span className="h-mono" style={{ color: H.ink2, fontSize: 11 }}>{r[0]}</span>
                    <span style={{ fontSize: 11.5, color: H.ink2 }}>{r[1]}</span>
                    <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r[2]}</span>
                    <span className="h-mono" style={{ color: H.ink3, fontSize: 11 }}>{r[3]}</span>
                    <span className="h-mono" style={{ fontSize: 11, color: r[5] === 'OVERDUE' ? H.bad : H.ink }}>{r[4]}</span>
                    <span><HStatus s={r[5]}/></span>
                    <span className="h-mono" style={{ fontSize: 11.5, textAlign: 'right', fontWeight: 500 }}>${r[6].toFixed(2)}</span>
                    <span style={{ textAlign: 'right', color: H.ink3, cursor: 'pointer' }}>⋯</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </HAppChrome>
  );
};

// ───────── SHOP DRAWINGS ─────────
// Subtabs: Current | In review | Archive | Templates
// Default: Current — grid of drawing thumbnails with version / reviewer chips
const HiShopDrawings = () => {
  const dwgs = [
    ['SD-001', 'Reception carcass assembly', 'L3 / Reception', 'v4', 'APPROVED', 'JR', '18 Apr'],
    ['SD-002', 'Reception front elevations', 'L3 / Reception', 'v3', 'SUBMITTED', 'RP', '19 Apr'],
    ['SD-003', 'Meeting rm island plan', 'L3 / Meeting Rm', 'v2', 'HOLD', 'RP', '19 Apr'],
    ['SD-004', 'Meeting rm door schedule', 'L3 / Meeting Rm', 'v1', 'REJECTED', 'JR', '17 Apr'],
    ['SD-005', 'Staff kitchen — upper cabs', 'L3 / Kitchen', 'v3', 'APPROVED', 'JR', '18 Apr'],
    ['SD-006', 'Staff kitchen — island counter', 'L3 / Kitchen', 'v2', 'LIVE', 'SO', '20 Apr'],
    ['SD-007', 'Breakout booth L assembly', 'L3 / Breakout', 'v2', 'APPROVED', 'JR', '18 Apr'],
    ['SD-008', 'Breakout booth R assembly', 'L3 / Breakout', 'v2', 'APPROVED', 'JR', '18 Apr'],
    ['SD-009', 'Print room joinery', 'L3 / Print', 'v1', 'SUBMITTED', 'RP', '20 Apr'],
  ];
  const userColors = { JR: '#3d6b8a', SO: '#7a5193', TA: '#6f7a51', BM: H.accent, RP: '#3f7d48' };
  const sub = [
    { key: 'current', label: 'Current', count: 22 },
    { key: 'review', label: 'In review', count: 5 },
    { key: 'archive', label: 'Archive' },
    { key: 'templates', label: 'Templates' },
  ];
  // simple sketch/line drawing placeholder generator
  const Blueprint = ({ seed = 1 }) => {
    const rnd = (n) => (Math.sin(seed * n * 12.9898) * 43758.5453) % 1;
    const r = (n) => Math.abs(rnd(n));
    return (
      <svg viewBox="0 0 180 110" style={{ width: '100%', height: '100%', background: '#f6f3ec', display: 'block' }}>
        <defs>
          <pattern id={`gd${seed}`} width="8" height="8" patternUnits="userSpaceOnUse">
            <path d="M 8 0 L 0 0 0 8" fill="none" stroke="#d8d2c2" strokeWidth="0.4"/>
          </pattern>
        </defs>
        <rect width="180" height="110" fill={`url(#gd${seed})`}/>
        <rect x={12 + r(1) * 20} y={18 + r(2) * 12} width={90 + r(3) * 40} height={50 + r(4) * 20} fill="none" stroke="#4b4438" strokeWidth="1.1"/>
        <rect x={22 + r(5) * 10} y={28 + r(6) * 6} width={36 + r(7) * 20} height={24 + r(8) * 12} fill="none" stroke="#4b4438" strokeWidth="0.7"/>
        <rect x={66 + r(9) * 14} y={28 + r(10) * 6} width={30 + r(11) * 18} height={24 + r(12) * 12} fill="none" stroke="#4b4438" strokeWidth="0.7"/>
        <line x1="12" y1={90 + r(13) * 4} x2="160" y2={90 + r(13) * 4} stroke="#c96442" strokeWidth="0.6" strokeDasharray="2,2"/>
        <text x="14" y="101" fontSize="5" fill="#8a8273" fontFamily="monospace">DIM {(1000 + r(15) * 2000).toFixed(0)} mm</text>
      </svg>
    );
  };
  return (
    <HAppChrome active="Shop Dwgs" subtabs={sub} activeSub="current" chromeExtra={
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '0 0 0 8px' }}>
        <button className="h-btn"><HIcon d={Icons.upload} size={11}/> Upload</button>
        <button className="h-btn h-btn-accent"><HIcon d={Icons.plus} size={11}/> New drawing</button>
      </div>
    }>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <HiPageHeader
          title="Shop Drawings · Alfred L3"
          sub="22 drawings across 7 rooms · 5 awaiting review."
          right={<>
            <button className="h-btn"><HIcon d={Icons.grid} size={11}/> Grid</button>
            <button className="h-btn" style={{ marginLeft: 6 }}><HIcon d={Icons.list} size={11}/> List</button>
          </>}
        />
        <div style={{ padding: '0 20px 10px', display: 'flex', gap: 6, alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '4px 9px', background: H.surface, border: `1px solid ${H.line}`, borderRadius: 5 }}>
            <HIcon d={Icons.search} size={11} stroke={H.ink3}/>
            <span style={{ fontSize: 11.5, color: H.ink3 }}>Find drawing by #, room, room name…</span>
          </div>
          <button className="h-btn">Room: All <HIcon d={Icons.chev} size={9}/></button>
          <button className="h-btn">Status: All <HIcon d={Icons.chev} size={9}/></button>
          <button className="h-btn">Reviewer: All <HIcon d={Icons.chev} size={9}/></button>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '0 20px 20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            {dwgs.map((d, i) => (
              <div key={d[0]} className="h-card" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column', cursor: 'pointer' }}>
                <div style={{ aspectRatio: '16 / 10', borderBottom: `1px solid ${H.line}`, position: 'relative' }}>
                  <Blueprint seed={i + 1}/>
                  <div style={{ position: 'absolute', top: 8, left: 8 }}><HStatus s={d[4]}/></div>
                  <div style={{ position: 'absolute', top: 8, right: 8, background: H.surface, border: `1px solid ${H.line}`, borderRadius: 3, padding: '1px 6px', fontSize: 10, fontWeight: 600, letterSpacing: 0.05, color: H.ink2 }} className="h-mono">{d[3]}</div>
                </div>
                <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span className="h-mono" style={{ fontSize: 10.5, color: H.ink3 }}>{d[0]}</span>
                    <div style={{ fontSize: 13, fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d[1]}</div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: H.ink3 }}>
                    <span>{d[2]}</span>
                    <div style={{ flex: 1 }}/>
                    <HAvatar label={d[5]} color={userColors[d[5]]} size={18}/>
                    <span className="h-mono">{d[6]}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </HAppChrome>
  );
};

// ───────── iSAMPLE ─────────
// Subtabs: Board | Approval ledger | Clients | Suppliers | Archive
// Default: Board — sample wall cards
const HiSamplebook = () => {
  const samples = [
    ['A-21', 'Oak veneer — Briggs 0412', 'Alfred L3 / Reception', 'APPROVED', '#c29075', 'JR', 'Signed 18 Apr'],
    ['A-22', 'Walnut banding — Briggs', 'Alfred L3 / Reception', 'APPROVED', '#6b6256', 'JR', 'Signed 18 Apr'],
    ['A-23', 'Laminate — Polytec Oxide', 'Alfred L3 / Meeting Rm', 'NOTE!', '#8a4434', 'BM', 'Waiting client'],
    ['A-24', 'Stone — Corian Deep Black', 'Alfred L3 / Kitchen', 'HOLD', '#2d2b27', 'BM', 'Client on leave'],
    ['M-12', 'Formica Grey 172', 'Monash FFT / Lab A', 'APPROVED', '#8b8b82', 'JR', 'Signed 16 Apr'],
    ['M-13', 'Soft-close runner', 'Monash FFT / Lab A', 'SUBMITTED', '#c8c4b9', 'RP', 'Awaiting sign'],
    ['M-14', 'Timber edge 3mm walnut', 'Monash FFT / Lab B', 'REJECTED', '#3c3028', 'JR', 'Too dark'],
    ['V-05', 'Acoustic panel grey', 'VSBA / Classroom', 'CLEAR', '#7a7366', 'BM', 'First spec'],
    ['T-09', 'Bullnose brass handle', 'Trentham / Kitchen', 'LIVE', '#b09268', 'MK', 'Ordering now'],
    ['T-10', 'Matte black flush D', 'Trentham / Pantry', 'APPROVED', '#2a2826', 'JR', 'Signed 17 Apr'],
  ];
  const userColors = { JR: '#3d6b8a', SO: '#7a5193', TA: '#6f7a51', BM: H.accent, RP: '#3f7d48', MK: '#b4443d' };
  const sub = [
    { key: 'board', label: 'Board', count: 28 },
    { key: 'ledger', label: 'Approval ledger' },
    { key: 'clients', label: 'Clients' },
    { key: 'suppliers', label: 'Suppliers' },
    { key: 'archive', label: 'Archive' },
  ];
  return (
    <HAppChrome active="iSample" subtabs={sub} activeSub="board" chromeExtra={
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '0 0 0 8px' }}>
        <button className="h-btn"><HIcon d={Icons.print} size={11}/> Print board</button>
        <button className="h-btn h-btn-accent"><HIcon d={Icons.plus} size={11}/> New sample</button>
      </div>
    }>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <HiPageHeader
          title="iSample — Sample Wall"
          sub="28 samples across 5 projects · 6 awaiting client · 2 rejected."
        />
        <div style={{ padding: '0 20px 10px', display: 'flex', gap: 6, alignItems: 'center' }}>
          <button className="h-btn h-btn-primary">All</button>
          <button className="h-btn">Awaiting client <span className="h-mono" style={{ color: H.warn, marginLeft: 4 }}>6</span></button>
          <button className="h-btn">Approved <span className="h-mono" style={{ color: H.good, marginLeft: 4 }}>18</span></button>
          <button className="h-btn">Rejected <span className="h-mono" style={{ color: H.bad, marginLeft: 4 }}>2</span></button>
          <div style={{ flex: 1 }}/>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '4px 9px', background: H.surface, border: `1px solid ${H.line}`, borderRadius: 5 }}>
            <HIcon d={Icons.search} size={11} stroke={H.ink3}/>
            <span style={{ fontSize: 11.5, color: H.ink3 }}>Find sample…</span>
          </div>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '0 20px 20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
            {samples.map((s, i) => (
              <div key={s[0]} className="h-card" style={{ overflow: 'hidden', cursor: 'pointer' }}>
                {/* swatch */}
                <div style={{ aspectRatio: '1', background: s[4], position: 'relative' }}>
                  {/* subtle tactile texture */}
                  <div style={{ position: 'absolute', inset: 0, background: 'repeating-linear-gradient(135deg, rgba(255,255,255,0.04) 0 2px, transparent 2px 6px)' }}/>
                  <div style={{ position: 'absolute', top: 8, left: 8 }}><HStatus s={s[3]}/></div>
                  <div style={{ position: 'absolute', top: 8, right: 8 }} className="h-mono">
                    <span style={{ background: 'rgba(255,255,255,0.92)', borderRadius: 3, padding: '1px 6px', fontSize: 10.5, fontWeight: 600, color: H.ink }}>{s[0]}</span>
                  </div>
                </div>
                <div style={{ padding: '10px 12px' }}>
                  <div style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s[1]}</div>
                  <div style={{ fontSize: 11, color: H.ink3, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s[2]}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
                    <HAvatar label={s[5]} color={userColors[s[5]]} size={18}/>
                    <span style={{ fontSize: 10.5, color: H.ink3, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s[6]}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </HAppChrome>
  );
};

Object.assign(window, { HiOrderbookOpen, HiShopDrawings, HiSamplebook });
