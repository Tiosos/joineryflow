// Hi-fi Dashboard — 5 directions (A default)
// A · Command deck (hero metrics + deliveries today + my day)
// B · Activity stream (feed-forward)
// C · My-Day Kanban
// D · Week timeline
// E · BrB staff board (who's in + where)

// shared
const HiPageHeader = ({ title, sub, right = null }) => (
  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, padding: '16px 20px 10px' }}>
    <div>
      <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: -0.3, lineHeight: 1.15 }}>{title}</div>
      {sub && <div style={{ fontSize: 12, color: H.ink2, marginTop: 2 }}>{sub}</div>}
    </div>
    <div style={{ flex: 1 }}/>
    {right}
  </div>
);

// ─────────── A — Command deck (DEFAULT) ───────────
const HiDashA = () => (
  <HAppChrome active="Dashboard">
    <div style={{ height: '100%', overflow: 'auto' }}>
      <HiPageHeader
        title="Monday, 20 Apr"
        sub="Good morning, Bill — 3 items need you before lunch."
        right={<>
          <button className="h-btn" style={{ marginRight: 6 }}><HIcon d={Icons.refresh} size={12}/> Sync</button>
          <button className="h-btn h-btn-accent"><HIcon d={Icons.plus} size={12}/> New project</button>
        </>}
      />
      <div style={{ padding: '0 20px 22px', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {[
          ['Open parts', '237', '+12', 'on Alfred L3 this week'],
          ['Orders in transit', '18', '2 overdue', 'incl. Hafele hinges'],
          ['Samples awaiting client', '6', '2 over 7d', '2 on Alfred, 4 on Monash'],
          ['Hours logged today', '3.0 / 8.0', '38%', 'team avg 2.4h'],
        ].map(([k, v, delta, foot], i) => (
          <div key={k} className="h-card" style={{ padding: 14 }}>
            <div className="h-eyebrow">{k}</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
              <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: -0.4 }} className="h-mono">{v}</div>
              <div style={{ fontSize: 11, color: i === 1 || i === 2 ? H.bad : H.good, fontWeight: 500 }}>{delta}</div>
            </div>
            <div style={{ fontSize: 11, color: H.ink3, marginTop: 4 }}>{foot}</div>
          </div>
        ))}
      </div>

      <div style={{ padding: '0 20px 20px', display: 'grid', gridTemplateColumns: '1.35fr 1fr', gap: 14 }}>
        {/* Left — My day */}
        <div className="h-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderBottom: `1px solid ${H.line}` }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>My day</div>
            <span className="h-pill">8 open · 2 done</span>
            <div style={{ flex: 1 }}/>
            <button className="h-btn h-btn-ghost" style={{ fontSize: 11 }}>Showing: All</button>
            <span style={{ fontSize: 11, color: H.accent, cursor: 'pointer' }}>View details →</span>
          </div>
          <div>
            {[
              ['ALFRED L3', 'Check & revise shop drawings for island', '3h', 'next', false, H.accent],
              ['ALFRED L3', 'Approve laminate sample #A-23 for reception wall', '1h', null, true, H.accent],
              ['VSBA MICKLEHAM', 'Procure acoustic panels — call Autex back', '2h', null, false, '#3d6b8a'],
              ['TRENTHAM', 'Call Hafele re: bullnose handles availability', '30m', null, false, '#b4443d'],
            ].map(([p, t, h, badge, done, color], i, arr) => (
              <div key={i} className="h-row-hover" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px', borderBottom: i < arr.length - 1 ? `1px solid ${H.line}` : 'none' }}>
                <div style={{ width: 14, height: 14, borderRadius: 4, border: `1.5px solid ${done ? H.good : H.ink4}`, display: 'flex', alignItems: 'center', justifyContent: 'center', background: done ? H.good : 'transparent', cursor: 'pointer', flexShrink: 0 }}>
                  {done && <span style={{ color: '#fff', fontSize: 9, fontWeight: 700 }}>✓</span>}
                </div>
                <span style={{ fontSize: 10, fontWeight: 600, color, letterSpacing: 0.04 }}>{p}</span>
                <span style={{ flex: 1, fontSize: 13, color: done ? H.ink3 : H.ink, textDecoration: done ? 'line-through' : 'none' }}>{t}</span>
                {badge && <span className="h-pill" style={{ background: H.accentSoft, color: H.accent, borderColor: H.accent + '33' }}>◎ {badge}</span>}
                <span className="h-mono" style={{ fontSize: 11, color: H.ink3, width: 30, textAlign: 'right' }}>{h}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right — Deliveries today */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0 }}>
          <div className="h-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderBottom: `1px solid ${H.line}` }}>
              <HIcon d={Icons.box} stroke={H.accent}/>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Deliveries today</div>
              <span className="h-pill">4</span>
              <div style={{ flex: 1 }}/>
              <span style={{ fontSize: 11, color: H.accent, cursor: 'pointer' }}>Orderbook →</span>
            </div>
            {[
              ['09:20', 'Briggs Veneer', 'ALFRED L3', 'ARRIVED', 'PO#2273-011'],
              ['11:00', 'Hafele', 'TRENTHAM', 'OVERDUE', 'PO#2289-003'],
              ['14:30', 'Polytec', 'MONASH FFT', 'LIVE', 'PO#2351-007'],
              ['16:00', 'Laminex', 'VSBA', 'LIVE', 'PO#2347-004'],
            ].map(([t, sup, proj, st, po], i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px', borderBottom: i < 3 ? `1px solid ${H.line}` : 'none' }}>
                <div className="h-mono" style={{ fontSize: 12, fontWeight: 600, width: 36 }}>{t}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 500 }}>{sup}</div>
                  <div style={{ fontSize: 10.5, color: H.ink3, letterSpacing: 0.04 }}>{proj} · <span className="h-mono">{po}</span></div>
                </div>
                <HStatus s={st}/>
              </div>
            ))}
          </div>

        </div>
      </div>

      {/* Team — unified: You, who's in today, recent activity */}
      <div style={{ padding: '0 20px 28px' }}>
        <div className="h-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderBottom: `1px solid ${H.line}` }}>
            <HIcon d={Icons.users} stroke={H.accent}/>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Team</div>
            <span className="h-pill">Today · 8</span>
            <div style={{ flex: 1 }}/>
            <span style={{ fontSize: 11, color: H.ink3 }}>Mon 20 Apr</span>
            <span style={{ fontSize: 11, color: H.accent, cursor: 'pointer', marginLeft: 10 }}>Team board →</span>
          </div>

          {(() => {
            const statusCol = { 'In': H.good, 'On site': H.info, 'Shop': H.accent, 'WFH': H.warn, 'Off': H.ink3 };
            const you = ['Bill Ma', 'BM', H.accent, 'In', 'Office', 'Estimating · heads-down till 12pm'];
            return (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px', background: H.accentSoft, borderBottom: `1px solid ${H.line}` }}>
                <div style={{ position: 'relative' }}>
                  <HAvatar label={you[1]} color={you[2]} size={34}/>
                  <span style={{ position: 'absolute', bottom: -1, right: -1, width: 11, height: 11, borderRadius: '50%', background: statusCol[you[3]], border: `2px solid ${H.surface}` }}/>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 600 }}>You · {you[0]}</div>
                  <div style={{ fontSize: 11, color: H.ink2 }}>
                    <b style={{ color: statusCol[you[3]], fontWeight: 600 }}>{you[3]}</b> · {you[4]} · <span style={{ color: H.ink3 }}>{you[5]}</span>
                  </div>
                </div>
                <button className="h-btn" style={{ background: H.surface }}><HIcon d={Icons.edit} size={10}/> Update status</button>
              </div>
            );
          })()}

          {/* who's in — tile strip */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 0, borderBottom: `1px solid ${H.line}` }}>
            {(() => {
              const statusCol = { 'In': H.good, 'On site': H.info, 'Shop': H.accent, 'WFH': H.warn, 'Off': H.ink3 };
              const team = [
                ['Jules Roh', 'JR', '#3d6b8a', 'On site', 'Alfred L3'],
                ['Rin Park', 'RP', '#3f7d48', 'In', 'Drafting'],
                ['Sam Oduya', 'SO', '#7a5193', 'Shop', 'Floor'],
                ['Mina Klee', 'MK', '#b4443d', 'In', 'Purchasing'],
                ['Priya Shah', 'PS', '#c48a2e', 'WFH', 'Sample specs'],
                ['Theo Akkad', 'TA', '#6f7a51', 'Shop', 'Assembly'],
                ['Dan Kowalski', 'DK', '#8f8b80', 'Off', 'PTO'],
              ];
              return team.map((p, i) => (
                <div key={p[0]} style={{ padding: '12px 10px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, borderRight: i < team.length - 1 ? `1px solid ${H.line}` : 'none' }}>
                  <div style={{ position: 'relative' }}>
                    <HAvatar label={p[1]} color={p[2]} size={32}/>
                    <span style={{ position: 'absolute', bottom: -1, right: -1, width: 10, height: 10, borderRadius: '50%', background: statusCol[p[3]], border: `2px solid ${H.surface}` }}/>
                  </div>
                  <div style={{ fontSize: 11.5, fontWeight: 500, textAlign: 'center' }}>{p[0].split(' ')[0]}</div>
                  <div style={{ fontSize: 10, color: statusCol[p[3]], fontWeight: 600 }}>{p[3]}</div>
                  <div style={{ fontSize: 10, color: H.ink3, textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%' }}>{p[4]}</div>
                </div>
              ));
            })()}
          </div>

          {/* recent activity sub-section */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', background: H.bg, borderBottom: `1px solid ${H.line}` }}>
            <HIcon d={Icons.activity} stroke={H.ink3} size={12}/>
            <div style={{ fontSize: 11, fontWeight: 600, color: H.ink2, letterSpacing: 0.04, textTransform: 'uppercase' }}>Recent activity</div>
            <div style={{ flex: 1 }}/>
            <span style={{ fontSize: 11, color: H.accent, cursor: 'pointer' }}>Full log →</span>
          </div>
          {[
            ['JR', '#3d6b8a', 'Jules Roh', 'approved 12 parts', 'Alfred L3 · island carcass', '18m', 'cutlist'],
            ['RP', '#3f7d48', 'Rin Park', 'uploaded shop dwg v4', 'VSBA wall assembly', '42m', 'drawings'],
            ['MK', '#b4443d', 'Mina Klee', 'placed order — $1,840', 'Hafele hinges · ETA Thu', '1h', 'orders'],
            ['SO', '#7a5193', 'Sam Oduya', 'scanned 58 kits', 'Shop-floor tablet · Alfred L3', '1h 20m', 'hardware'],
            ['BM', H.accent, 'You', 'set sample A-23 to NOTE!', 'Alfred L3 · Meeting Rm', '2h', 'samples'],
          ].map(([in_, col, name, verb, what, when, tag], i, arr) => (
            <div key={i} className="h-row-hover" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderBottom: i < arr.length - 1 ? `1px solid ${H.line}` : 'none' }}>
              <HAvatar label={in_} color={col} size={26}/>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}><b style={{ fontWeight: 600 }}>{name}</b> <span style={{ color: H.ink2 }}>{verb}</span></div>
                <div style={{ fontSize: 11, color: H.ink3, marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{what}</div>
              </div>
              <span className="h-pill">{tag}</span>
              <span className="h-mono" style={{ fontSize: 10.5, color: H.ink3, width: 52, textAlign: 'right' }}>{when}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  </HAppChrome>
);

// ─────────── B — Activity stream ───────────
const HiDashB = () => (
  <HAppChrome active="Dashboard">
    <div style={{ padding: 20, height: '100%', overflow: 'auto', display: 'grid', gridTemplateColumns: '1fr 300px', gap: 14 }}>
      <div>
        <HiPageHeader title="Activity" sub="Everything happening across your workspace, newest first." />
        {/* filter chips */}
        <div style={{ display: 'flex', gap: 6, padding: '0 0 12px' }}>
          {['All', 'Mentions', 'Orders', 'Samples', 'Drawings', 'Cutlist', 'People'].map((t, i) => (
            <span key={t} className="h-pill" style={i === 0 ? { background: H.ink, color: H.bg, borderColor: H.ink } : {}}>{t}</span>
          ))}
        </div>

        {[
          ['today', [
            ['09:41', 'JR', '#3d6b8a', 'Jules Roh', 'approved 12 parts', 'Alfred L3 → island carcass', 'cutlist'],
            ['09:12', 'MK', '#b4443d', 'Mina Klee', 'placed order — $1,840', 'Hafele hinges · ETA Thu', 'orders'],
            ['08:55', 'System', H.ink3, 'System', 'flagged 2 overdue deliveries', 'Polytec + Hafele', 'orders'],
            ['08:20', 'RP', '#3f7d48', 'Rin Park', 'uploaded dwg v4', 'VSBA wall assembly', 'drawings'],
          ]],
          ['yesterday', [
            ['17:14', 'BM', H.accent, 'You', 'left 3 notes', 'On Trentham cutlist rev-C', 'cutlist'],
            ['14:02', 'SO', '#7a5193', 'Sam Oduya', 'scanned 58 kits', 'Shop-floor tablet', 'hardware'],
            ['11:30', 'JR', '#3d6b8a', 'Jules Roh', 'marked sample A-19 HOLD', 'client feedback pending', 'samples'],
          ]],
        ].map(([day, items]) => (
          <div key={day}>
            <div className="h-eyebrow" style={{ margin: '10px 0 6px' }}>{day}</div>
            <div className="h-card">
              {items.map((it, i) => (
                <div key={i} style={{ display: 'flex', gap: 10, padding: '11px 14px', borderBottom: i < items.length - 1 ? `1px solid ${H.line}` : 'none' }}>
                  <HAvatar label={it[1]} color={it[2]} size={26}/>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5 }}>
                      <b style={{ fontWeight: 600 }}>{it[3]}</b> <span style={{ color: H.ink2 }}>{it[4]}</span>
                    </div>
                    <div style={{ fontSize: 11.5, color: H.ink3, marginTop: 2 }}>{it[5]}</div>
                  </div>
                  <span className="h-pill" style={{ alignSelf: 'flex-start', background: H.surfaceAlt }}>{it[6]}</span>
                  <span className="h-mono" style={{ fontSize: 11, color: H.ink3, alignSelf: 'flex-start' }}>{it[0]}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* right rail */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div className="h-card" style={{ padding: 14 }}>
          <div className="h-eyebrow" style={{ marginBottom: 8 }}>Your pins</div>
          {['Alfred L3 — cutlist rev C', 'Trentham samples board', 'Hafele weekly rollup'].map(x => (
            <div key={x} style={{ fontSize: 12, padding: '6px 0', borderBottom: `1px dashed ${H.line}`, display: 'flex', alignItems: 'center', gap: 6 }}>
              <HIcon d={Icons.tag} size={11} stroke={H.accent}/> {x}
            </div>
          ))}
        </div>
        <div className="h-card" style={{ padding: 14 }}>
          <div className="h-eyebrow" style={{ marginBottom: 8 }}>Upcoming deliveries</div>
          {[['Thu', 'Hafele · $1,840'], ['Fri', 'Polytec · $940'], ['Mon', 'Briggs Veneer · $3,210']].map(([d, s]) => (
            <div key={d} style={{ fontSize: 12, padding: '6px 0', borderBottom: `1px dashed ${H.line}`, display: 'flex', gap: 8 }}>
              <span className="h-mono" style={{ width: 30, color: H.ink3 }}>{d}</span>{s}
            </div>
          ))}
        </div>
      </div>
    </div>
  </HAppChrome>
);

// ─────────── C — My-Day Kanban ───────────
const HiDashC = () => {
  const cols = [
    ['Backlog', H.ink3, [
      ['TRENTHAM', 'Call Hafele re: bullnose handles'],
      ['ALFRED L3', 'Draft recip letter for site visit'],
      ['7SS FLINDERS', 'Start rev-E cutlist for kitchen'],
    ]],
    ['Today', H.accent, [
      ['ALFRED L3', 'Check & revise island shop dwgs', '3h', true],
      ['ALFRED L3', 'Approve laminate A-23', '1h'],
      ['MONASH FFT', 'Confirm site measure Thurs'],
    ]],
    ['In progress', H.info, [
      ['VSBA MICKLEHAM', 'Procure acoustic panels', '1h'],
    ]],
    ['Waiting', H.warn, [
      ['TRENTHAM', 'Client decision on handles', '2d'],
      ['MONASH FFT', 'Client approval on A-19', '5d'],
    ]],
    ['Done', H.good, [
      ['ALFRED L3', 'Send Jules the sample pack'],
      ['7SS FLINDERS', 'Approve timber sample'],
    ]],
  ];
  return (
    <HAppChrome active="Dashboard">
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <HiPageHeader
          title="My day"
          sub="Drag cards between stages as you work."
          right={<>
            <button className="h-btn"><HIcon d={Icons.filter} size={11}/> Me</button>
            <button className="h-btn h-btn-accent" style={{ marginLeft: 6 }}><HIcon d={Icons.plus} size={11}/> Add card</button>
          </>}
        />
        <div style={{ flex: 1, overflow: 'auto', padding: '0 20px 20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, minHeight: '100%' }}>
            {cols.map(([name, col, items]) => (
              <div key={name} style={{ background: H.surfaceAlt, borderRadius: 8, padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: col }}/>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{name}</div>
                  <span className="h-pill" style={{ padding: '0 6px', fontSize: 10 }}>{items.length}</span>
                  <div style={{ flex: 1 }}/>
                  <span style={{ color: H.ink3, fontSize: 14, cursor: 'pointer' }}>+</span>
                </div>
                {items.map((it, i) => (
                  <div key={i} style={{ background: H.surface, border: `1px solid ${H.line}`, borderRadius: 6, padding: 9, boxShadow: it[3] ? `0 0 0 1.5px ${H.accent}` : '0 1px 0 rgba(0,0,0,0.02)' }}>
                    <div style={{ fontSize: 9.5, letterSpacing: 0.05, fontWeight: 600, color: H.ink3, marginBottom: 3 }}>{it[0]}</div>
                    <div style={{ fontSize: 12.5, fontWeight: 500, lineHeight: 1.3 }}>{it[1]}</div>
                    {it[2] && <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
                      <HIcon d={Icons.clock} size={10} stroke={H.ink3}/>
                      <span className="h-mono" style={{ fontSize: 10.5, color: H.ink3 }}>{it[2]}</span>
                      <div style={{ flex: 1 }}/>
                      <HAvatar label="BM" size={16}/>
                    </div>}
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

// ─────────── D — Week timeline ───────────
const HiDashD = () => {
  // Full-project Gantt for every cutlist in this project
  const days = ['Mon 20', 'Tue 21', 'Wed 22', 'Thu 23', 'Fri 24', 'Mon 27', 'Tue 28', 'Wed 29', 'Thu 30', 'Fri 01'];
  // Cutlist rows: [No., title, colour, segments [start-day, width-days, label]]
  // Stages: Draft → Review → Cut → QC → Pack
  const lists = [
    ['297885', 'Island carcass · L3 kitchen', H.accent, [
      [0, 1, 'Draft'], [1, 0.8, 'Review'], [2, 2, 'Cut'], [4, 0.8, 'QC'], [5, 1, 'Pack'],
    ]],
    ['295433', 'Reception wall · reeded oak', '#3d6b8a', [
      [0.5, 1.5, 'Draft rev-C'], [2, 1, 'Review'], [3.2, 2.3, 'Cut'], [5.8, 1, 'QC'],
    ]],
    ['294466', 'Meeting rm A · bench + tambour', '#7a5193', [
      [1, 1.2, 'Draft'], [2.5, 1, 'Review'], [4, 1.8, 'Cut'], [6, 1, 'QC'], [7.2, 1.3, 'Pack'],
    ]],
    ['299087', 'Joinery pkg 2 · breakout', '#3f7d48', [
      [0, 0.6, 'Site dims'], [1, 1.8, 'Draft'], [3.2, 1, 'Review'], [4.5, 2.5, 'Cut'], [7.2, 1.2, 'QC'],
    ]],
    ['298124', 'Vanities · L3 WCs', '#c48a2e', [
      [2, 1.4, 'Draft'], [3.8, 1, 'Review'], [5.2, 2, 'Cut'], [7.5, 1, 'QC'],
    ]],
    ['296701', 'Storage wall · archive', '#b4443d', [
      [0, 2, 'Cut'], [2.2, 1, 'QC'], [3.5, 1.2, 'Pack'],
    ]],
  ];
  const stageBg = { 'Draft': '#94a3b8', 'Draft rev-C': '#94a3b8', 'Site dims': '#94a3b8',
    'Review': '#c48a2e', 'Cut': H.accent, 'QC': '#3d6b8a', 'Pack': '#3f7d48' };
  const todayDay = 0; // Mon
  return (
    <HAppChrome active="Dashboard">
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <HiPageHeader title="Alfred L3 — cutlist schedule" sub="All 6 cutlists in this project · 2-week rolling view" right={<>
          <button className="h-btn h-btn-ghost" style={{ fontSize: 11 }}>Project: Alfred L3 ▾</button>
          <button className="h-btn"><HIcon d={Icons.chev} size={11}/> Prev</button>
          <button className="h-btn">Today</button>
          <button className="h-btn"><HIcon d={Icons.chev} size={11}/> Next</button>
        </>}/>
        {/* stage legend */}
        <div style={{ padding: '0 20px 10px', display: 'flex', gap: 14, alignItems: 'center' }}>
          <span className="h-eyebrow">Stage</span>
          {['Draft', 'Review', 'Cut', 'QC', 'Pack'].map(s => (
            <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: H.ink2 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: stageBg[s] }}/> {s}
            </span>
          ))}
          <div style={{ flex: 1 }}/>
          <span style={{ fontSize: 11, color: H.ink3 }}>Bars coloured by stage · left rail shows project colour</span>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '0 20px 20px' }}>
          <div className="h-card" style={{ overflow: 'hidden' }}>
            {/* header row */}
            <div style={{ display: 'grid', gridTemplateColumns: `260px repeat(${days.length}, 1fr)`, borderBottom: `1px solid ${H.line}`, background: H.surfaceAlt }}>
              <div style={{ padding: '10px 12px', fontSize: 10, fontWeight: 600, color: H.ink3, letterSpacing: 0.08, textTransform: 'uppercase' }}>Cutlist</div>
              {days.map((d, i) => (
                <div key={d} style={{ padding: '10px 10px', fontSize: 11, fontWeight: 600, color: H.ink2, borderLeft: `1px solid ${H.line}`, background: i === todayDay ? '#fff' : 'transparent' }}>
                  {d}{i === todayDay && <div style={{ fontSize: 9, color: H.accent, fontWeight: 700, marginTop: 1 }}>TODAY</div>}
                </div>
              ))}
            </div>
            {lists.map(([no, title, col, segs], ri) => (
              <div key={no} style={{ display: 'grid', gridTemplateColumns: `260px repeat(${days.length}, 1fr)`, height: 62, borderBottom: ri < lists.length - 1 ? `1px solid ${H.line}` : 'none', position: 'relative' }}>
                <div style={{ padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10, borderRight: `1px solid ${H.line}` }}>
                  <span style={{ width: 4, height: 38, borderRadius: 2, background: col, flexShrink: 0 }}/>
                  <div style={{ minWidth: 0 }}>
                    <div className="h-mono" style={{ fontSize: 12.5, fontWeight: 600 }}>#{no}</div>
                    <div style={{ fontSize: 11, color: H.ink2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</div>
                  </div>
                </div>
                <div style={{ gridColumn: `2 / -1`, position: 'relative' }}>
                  {/* day gridlines */}
                  {days.map((_, i) => (
                    <div key={i} style={{ position: 'absolute', left: `${(i / days.length) * 100}%`, top: 0, bottom: 0, borderLeft: `1px solid ${H.line}` }}/>
                  ))}
                  {/* today vertical line */}
                  <div style={{ position: 'absolute', left: `${((todayDay + 0.5) / days.length) * 100}%`, top: 0, bottom: 0, borderLeft: `1.5px dashed ${H.accent}`, opacity: 0.7 }}/>
                  {segs.map(([start, w, label], i) => (
                    <div key={i} title={`${label} · ${no}`} style={{ position: 'absolute', top: 12, height: 38, left: `${(start / days.length) * 100}%`, width: `${(w / days.length) * 100}%`, background: stageBg[label] || col, borderRadius: 5, padding: '0 10px', display: 'flex', alignItems: 'center', color: '#fff', fontSize: 11, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', boxShadow: '0 1px 2px rgba(0,0,0,0.18)', border: `1px solid rgba(0,0,0,0.05)` }}>
                      {label}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </HAppChrome>
  );
};

// ─────────── E — BrB staff board ───────────
const HiDashE = () => {
  const staff = [
    ['Bill Ma', 'BM', H.accent, 'In', 'Office', 'Estimating'],
    ['Jules Roh', 'JR', '#3d6b8a', 'On site', 'Alfred L3', 'Until 2pm'],
    ['Rin Park', 'RP', '#3f7d48', 'In', 'Drafting', 'Heads-down'],
    ['Sam Oduya', 'SO', '#7a5193', 'Shop', 'Floor', 'Kit pulls'],
    ['Mina Klee', 'MK', '#b4443d', 'In', 'Office', 'Purchasing'],
    ['Theo Akkad', 'TA', '#6f7a51', 'Shop', 'Floor', 'Assembly'],
    ['Priya Shah', 'PS', '#c48a2e', 'WFH', '—', 'Sample specs'],
    ['Dan Kowalski', 'DK', '#8f8b80', 'Off', '—', 'PTO'],
  ];
  const statusCol = { 'In': H.good, 'On site': H.info, 'Shop': H.accent, 'WFH': H.warn, 'Off': H.ink3 };
  return (
    <HAppChrome active="Dashboard">
      <div style={{ height: '100%', overflow: 'auto' }}>
        <HiPageHeader title="Team · this morning" sub="Who's in, where they are, what they're doing." right={
          <><button className="h-btn"><HIcon d={Icons.plus} size={11}/> Update my status</button></>
        }/>
        {/* Summary */}
        <div style={{ padding: '0 20px 16px', display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10 }}>
          {[['In office', 4, H.good], ['On site', 1, H.info], ['On shop floor', 2, H.accent], ['WFH', 1, H.warn], ['Off', 1, H.ink3]].map(([k, v, c]) => (
            <div key={k} className="h-card" style={{ padding: 11, display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ width: 9, height: 9, borderRadius: '50%', background: c }}/>
              <div>
                <div className="h-mono" style={{ fontSize: 17, fontWeight: 600 }}>{v}</div>
                <div style={{ fontSize: 11, color: H.ink2 }}>{k}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Left: my out-of-office log · Right: staff cards */}
        <div style={{ padding: '0 20px 20px', display: 'grid', gridTemplateColumns: '340px 1fr', gap: 14 }}>
          {/* My recent out-of-office */}
          <div className="h-card" style={{ alignSelf: 'start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderBottom: `1px solid ${H.line}` }}>
              <HIcon d={Icons.room} stroke={H.accent}/>
              <div style={{ fontSize: 13, fontWeight: 600 }}>My out-of-office log</div>
              <span className="h-pill">recent</span>
              <div style={{ flex: 1 }}/>
              <button className="h-btn h-btn-ghost" style={{ fontSize: 11 }}><HIcon d={Icons.plus} size={10}/> Log</button>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px', background: H.accentSoft, borderBottom: `1px solid ${H.line}` }}>
              <HAvatar label="BM" color={H.accent} size={30}/>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600 }}>You · Bill Ma</div>
                <div style={{ fontSize: 11, color: H.ink2 }}><b style={{ color: H.good, fontWeight: 600 }}>In</b> · Office · Estimating</div>
              </div>
            </div>
            {[
              ['Fri 17 Apr', 'On site', 'Alfred L3', 'Site meeting · joinery handover', H.info],
              ['Thu 16 Apr', 'Shop', 'Floor', 'QC walk-through with Theo', H.accent],
              ['Wed 15 Apr', 'On site', 'Monash FFT', 'Measure check · L2 corridor', H.info],
              ['Mon 13 Apr', 'WFH', '—', 'Drafting — VSBA shop dwg v3', H.warn],
              ['Fri 10 Apr', 'On site', 'Trentham', 'Client review · bench sample', H.info],
              ['Thu 09 Apr', 'Off', '—', 'PTO · half day', H.ink3],
            ].map(([date, st, loc, note, col], i, arr) => (
              <div key={i} className="h-row-hover" style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 14px', borderBottom: i < arr.length - 1 ? `1px solid ${H.line}` : 'none' }}>
                <div className="h-mono" style={{ fontSize: 10.5, color: H.ink3, width: 62, flexShrink: 0, paddingTop: 1 }}>{date}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontWeight: 600, color: col }}>{st}</span>
                    <span style={{ color: H.ink3 }}>·</span>
                    <span style={{ color: H.ink2 }}>{loc}</span>
                  </div>
                  <div style={{ fontSize: 11, color: H.ink3, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{note}</div>
                </div>
              </div>
            ))}
            <div style={{ padding: '9px 14px', fontSize: 11, color: H.accent, cursor: 'pointer', textAlign: 'center' }}>View full history →</div>
          </div>

          {/* Staff cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, alignContent: 'start' }}>
            {staff.map(([name, in_, col, st, loc, note]) => (
              <div key={name} className="h-card" style={{ padding: 12, display: 'flex', gap: 10, alignItems: 'center' }}>
                <div style={{ position: 'relative' }}>
                  <HAvatar label={in_} color={col} size={36}/>
                  <span style={{ position: 'absolute', bottom: -1, right: -1, width: 11, height: 11, borderRadius: '50%', background: statusCol[st], border: `2px solid ${H.surface}` }}/>
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{name}</div>
                  <div style={{ fontSize: 11, color: H.ink2 }}><b style={{ color: statusCol[st], fontWeight: 600 }}>{st}</b> · {loc}</div>
                  <div style={{ fontSize: 10.5, color: H.ink3, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{note}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Shop floor strip */}
        <div style={{ padding: '0 20px 24px' }}>
          <div className="h-card">
            <div style={{ padding: '12px 14px', borderBottom: `1px solid ${H.line}`, display: 'flex', alignItems: 'center', gap: 10 }}>
              <HIcon d={Icons.activity} stroke={H.accent}/>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Shop floor — live stations</div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', borderCollapse: 'collapse' }}>
              {[
                ['Beam saw', 'Running', 'Alfred L3', '78%', H.good],
                ['Edgebander', 'Idle', '—', '0%', H.ink3],
                ['CNC', 'Running', 'VSBA', '52%', H.good],
                ['Assembly', 'Blocked', 'Hafele late', '—', H.bad],
              ].map(([n, s, proj, pct, col], i) => (
                <div key={n} style={{ padding: 12, borderRight: i < 3 ? `1px solid ${H.line}` : 'none' }}>
                  <div className="h-eyebrow">{n}</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: col, marginTop: 4 }}>{s}</div>
                  <div style={{ fontSize: 11, color: H.ink2 }}>{proj}</div>
                  <div style={{ height: 4, background: H.surfaceAlt, borderRadius: 2, marginTop: 8, overflow: 'hidden' }}>
                    <div style={{ width: pct, height: '100%', background: col }}/>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </HAppChrome>
  );
};

Object.assign(window, { HiDashA, HiDashB, HiDashC, HiDashD, HiDashE });
