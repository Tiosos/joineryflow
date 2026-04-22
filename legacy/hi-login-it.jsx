// Hi-fi screen set 1: Login, IT Management, Dashboard (A default + B/C/D/E)
// Uses H palette, HAppChrome, HStatus, HIcon, Icons, HAvatar from wireframes-hifi.jsx

// ────────────────── LOGIN ──────────────────
const HiLogin = () => (
  <div className="h-root" style={{ height: '100%', background: H.bg, display: 'flex' }}>
    {/* Left — brand panel */}
    <div style={{ flex: 1, background: H.ink, color: H.bg, padding: 40, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', position: 'relative', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 28, height: 28, borderRadius: 7, background: H.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 700 }}>◴</div>
        <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: -0.2 }}>Joinery<span style={{ color: H.accent }}>Flow</span></div>
      </div>
      <div style={{ position: 'relative', zIndex: 2 }}>
        <div style={{ fontSize: 28, lineHeight: 1.15, fontWeight: 600, letterSpacing: -0.5, maxWidth: 420, marginBottom: 14 }}>
          Every joint, every delivery, every drawing — in one place.
        </div>
        <div style={{ fontSize: 13, color: '#a8a49a', maxWidth: 380, lineHeight: 1.55 }}>
          Built for custom joinery shops. Cutlists, hardware, samples, shop drawings, and orderbooks move together — not in separate spreadsheets.
        </div>
      </div>
      <div style={{ display: 'flex', gap: 28, fontSize: 11, color: '#8f8b80' }}>
        <div><div style={{ color: H.bg, fontWeight: 600, fontSize: 13 }}>14</div>projects live</div>
        <div><div style={{ color: H.bg, fontWeight: 600, fontSize: 13 }}>2,391</div>parts tracked</div>
        <div><div style={{ color: H.bg, fontWeight: 600, fontSize: 13 }}>38</div>suppliers</div>
      </div>
      {/* decorative grid */}
      <div aria-hidden style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)', backgroundSize: '28px 28px', pointerEvents: 'none' }}/>
    </div>
    {/* Right — form */}
    <div style={{ width: 420, background: H.surface, padding: '48px 44px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: -0.3 }}>Welcome back</div>
      <div style={{ fontSize: 13, color: H.ink2, marginTop: 4, marginBottom: 28 }}>Sign in to continue to your workshop.</div>

      <label style={{ fontSize: 11, fontWeight: 600, color: H.ink2, letterSpacing: 0.04 }}>EMAIL</label>
      <input className="h-input" defaultValue="bill.ma@joineryflow.co" style={{ marginTop: 4, marginBottom: 14, padding: 8 }}/>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <label style={{ fontSize: 11, fontWeight: 600, color: H.ink2, letterSpacing: 0.04 }}>PASSWORD</label>
        <a style={{ fontSize: 11, color: H.accent, textDecoration: 'none', cursor: 'pointer' }}>Forgot?</a>
      </div>
      <input className="h-input" type="password" defaultValue="••••••••••" style={{ marginTop: 4, marginBottom: 14, padding: 8 }}/>

      <label style={{ fontSize: 11, fontWeight: 600, color: H.ink2, letterSpacing: 0.04 }}>WORKSPACE</label>
      <div style={{ display: 'flex', alignItems: 'center', border: `1px solid ${H.line}`, borderRadius: 5, marginTop: 4, marginBottom: 22 }}>
        <div style={{ padding: '8px 10px', fontSize: 12, flex: 1 }}>hartwood-joinery</div>
        <HIcon d={Icons.chev} size={13} stroke={H.ink3}/>
        <div style={{ width: 6 }}/>
      </div>

      <button className="h-btn h-btn-primary" style={{ padding: '9px 12px', fontSize: 13, justifyContent: 'center', width: '100%' }}>Sign in</button>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '22px 0 14px', color: H.ink3, fontSize: 11 }}>
        <div style={{ height: 1, background: H.line, flex: 1 }}/>or<div style={{ height: 1, background: H.line, flex: 1 }}/>
      </div>
      <button className="h-btn" style={{ justifyContent: 'center', padding: '8px 12px', fontSize: 12 }}>
        <HIcon d={Icons.shield} size={13}/> Continue with SSO
      </button>

      <div style={{ flex: 1 }}/>
      <div style={{ fontSize: 11, color: H.ink3, textAlign: 'center', marginTop: 22 }}>
        New shop? <span style={{ color: H.ink, fontWeight: 500, cursor: 'pointer' }}>Request access</span>
      </div>
    </div>
  </div>
);

// ────────────────── IT MANAGEMENT ──────────────────
const HiITManagement = () => {
  const users = [
    ['Bill Ma', 'bill.ma@', 'Estimator', 'Admin', 'Active', 'Just now', H.accent],
    ['Jules Roh', 'jules.r@', 'Project Manager', 'Manager', 'Active', '4m ago', '#3d6b8a'],
    ['Rin Park', 'rin.p@', 'CAD / Drafter', 'Editor', 'Active', '12m ago', '#3f7d48'],
    ['Sam Oduya', 'sam.o@', 'Shop Floor Lead', 'Editor', 'Active', '18m ago', '#7a5193'],
    ['Mina Klee', 'mina.k@', 'Purchasing', 'Editor', 'Active', '1h ago', '#b4443d'],
    ['Theo Akkad', 'theo.a@', 'Carpenter', 'Viewer', 'Active', '2h ago', '#6f7a51'],
    ['Priya Shah', 'priya.s@', 'Designer', 'Editor', 'Invited', '—', '#c48a2e'],
    ['Dan Kowalski', 'dan.k@', 'Site Supervisor', 'Editor', 'Suspended', '3d ago', '#8f8b80'],
  ];
  const sub = [
    { key: 'users', label: 'Users', count: 12 },
    { key: 'roles', label: 'Roles & Permissions' },
    { key: 'inv', label: 'Invitations', count: 3 },
    { key: 'int', label: 'Integrations' },
    { key: 'audit', label: 'Audit Log' },
    { key: 'bill', label: 'Billing' },
  ];
  return (
    <div className="h-root" style={{ height: '100%', display: 'flex', flexDirection: 'column', background: H.bg }}>
      {/* top bar mimicking app chrome but surfaced as a Settings view */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '8px 14px', borderBottom: `1px solid ${H.line}`, background: H.surface, gap: 12, height: 48, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 24, height: 24, borderRadius: 6, background: H.ink, color: H.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700 }}>◴</div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Joinery<span style={{ color: H.accent }}>Flow</span></div>
          <span style={{ color: H.ink4, margin: '0 4px' }}>/</span>
          <span style={{ fontSize: 13, fontWeight: 500, color: H.ink2 }}>IT Management</span>
        </div>
        <div style={{ flex: 1 }}/>
        <span className="h-pill" style={{ background: H.accentSoft, color: H.accent, borderColor: H.accent + '33' }}>◉ Admin mode</span>
        <HAvatar label="BM" size={28} />
      </div>
      {/* subtabs */}
      <div style={{ display: 'flex', padding: '0 20px', borderBottom: `1px solid ${H.line}`, background: H.surface, gap: 0, flexShrink: 0 }}>
        {sub.map((t, i) => (
          <div key={t.key} className={`h-subtab ${i === 0 ? 'h-subtab-active' : ''}`}>
            {t.label}{t.count != null && <span style={{ color: H.ink3, marginLeft: 6, fontWeight: 500 }}>{t.count}</span>}
          </div>
        ))}
      </div>

      {/* body */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* aside */}
        <div style={{ width: 240, borderRight: `1px solid ${H.line}`, background: H.surface, padding: '18px 14px', flexShrink: 0 }}>
          <div className="h-eyebrow" style={{ marginBottom: 8 }}>Workspace</div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Hartwood Joinery Co.</div>
          <div style={{ fontSize: 11, color: H.ink3, marginTop: 2 }}>Plan · Studio · 12 seats</div>

          <div style={{ height: 1, background: H.line, margin: '16px 0' }}/>

          <div className="h-eyebrow" style={{ marginBottom: 8 }}>Quick stats</div>
          {[['Active users', '10'], ['Pending invites', '3'], ['Suspended', '1'], ['Last audit', '12m ago']].map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '5px 0', borderBottom: `1px dashed ${H.line}` }}>
              <span style={{ color: H.ink2 }}>{k}</span><span className="h-mono" style={{ fontWeight: 500 }}>{v}</span>
            </div>
          ))}
        </div>

        {/* main */}
        <div style={{ flex: 1, padding: 20, overflow: 'auto', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: -0.2 }}>Users</div>
              <div style={{ fontSize: 12, color: H.ink2, marginTop: 2 }}>Manage who can access this workspace and what they can do.</div>
            </div>
            <div style={{ flex: 1 }}/>
            <button className="h-btn" style={{ marginRight: 6 }}><HIcon d={Icons.download} size={12}/> Export</button>
            <button className="h-btn h-btn-accent"><HIcon d={Icons.plus} size={12}/> Invite user</button>
          </div>

          {/* filter strip */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 9px', background: H.surface, border: `1px solid ${H.line}`, borderRadius: 5, width: 240 }}>
              <HIcon d={Icons.search} size={12} stroke={H.ink3}/>
              <span style={{ fontSize: 12, color: H.ink3 }}>Search users, emails…</span>
            </div>
            <button className="h-btn">Role: Any <HIcon d={Icons.chev} size={10} /></button>
            <button className="h-btn">Status: Any <HIcon d={Icons.chev} size={10} /></button>
            <div style={{ flex: 1 }}/>
            <span style={{ fontSize: 11, color: H.ink3 }}>{users.length} users</span>
          </div>

          {/* table */}
          <div className="h-card" style={{ overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '24px 2.2fr 1.6fr 1fr 1fr 1fr 40px', gap: 12, padding: '9px 14px', background: H.surfaceAlt, fontSize: 10.5, fontWeight: 600, color: H.ink3, letterSpacing: 0.06, textTransform: 'uppercase', borderBottom: `1px solid ${H.line}` }}>
              <span></span><span>User</span><span>Title</span><span>Role</span><span>Status</span><span>Last active</span><span></span>
            </div>
            {users.map(([name, email, title, role, status, last, color], i) => (
              <div key={i} className="h-row-hover" style={{ display: 'grid', gridTemplateColumns: '24px 2.2fr 1.6fr 1fr 1fr 1fr 40px', gap: 12, padding: '10px 14px', borderBottom: i < users.length - 1 ? `1px solid ${H.line}` : 'none', fontSize: 12.5, alignItems: 'center' }}>
                <input type="checkbox" style={{ accentColor: H.accent }}/>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
                  <HAvatar label={name.split(' ').map(w => w[0]).join('').slice(0, 2)} color={color} size={26}/>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</div>
                    <div style={{ fontSize: 11, color: H.ink3 }}>{email}hartwood.co</div>
                  </div>
                </div>
                <span style={{ color: H.ink2 }}>{title}</span>
                <span>
                  <span className="h-pill" style={role === 'Admin' ? { background: H.accentSoft, color: H.accent, borderColor: H.accent + '33' } : role === 'Manager' ? { background: H.infoSoft, color: H.info, borderColor: H.info + '33' } : {}}>
                    {role === 'Admin' && <HIcon d={Icons.key} size={10}/>}
                    {role}
                  </span>
                </span>
                <span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: status === 'Active' ? H.good : status === 'Invited' ? H.warn : H.ink3 }}/>
                    {status}
                  </span>
                </span>
                <span className="h-mono" style={{ color: H.ink3, fontSize: 11.5 }}>{last}</span>
                <span style={{ textAlign: 'right', color: H.ink3, cursor: 'pointer' }}>⋯</span>
              </div>
            ))}
          </div>

          {/* permissions panel teaser */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 14, marginTop: 18 }}>
            <div className="h-card" style={{ padding: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <HIcon d={Icons.shield} stroke={H.accent}/>
                <div style={{ fontWeight: 600, fontSize: 13 }}>Role permissions — quick view</div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1.4fr repeat(4, 1fr)', fontSize: 11.5, rowGap: 6, columnGap: 8 }}>
                <span></span>
                {['Admin', 'Manager', 'Editor', 'Viewer'].map(r => <span key={r} style={{ fontWeight: 600, color: H.ink2, textAlign: 'center' }}>{r}</span>)}
                {[
                  ['Create projects', [1, 1, 0, 0]],
                  ['Edit cutlist / drawings', [1, 1, 1, 0]],
                  ['Place orders', [1, 1, 0, 0]],
                  ['Approve samples', [1, 1, 0, 0]],
                  ['Manage users', [1, 0, 0, 0]],
                  ['View activity log', [1, 1, 1, 1]],
                ].map(([lab, row]) => (
                  <React.Fragment key={lab}>
                    <span style={{ color: H.ink2 }}>{lab}</span>
                    {row.map((v, i) => (
                      <span key={i} style={{ textAlign: 'center', color: v ? H.good : H.ink4 }}>{v ? '●' : '○'}</span>
                    ))}
                  </React.Fragment>
                ))}
              </div>
            </div>
            <div className="h-card" style={{ padding: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <HIcon d={Icons.activity} stroke={H.info}/>
                <div style={{ fontWeight: 600, fontSize: 13 }}>Recent activity</div>
                <div style={{ flex: 1 }}/>
                <span style={{ fontSize: 11, color: H.accent, cursor: 'pointer' }}>View log →</span>
              </div>
              {[
                ['Bill Ma', 'promoted Rin Park to Editor', '2m ago'],
                ['Jules Roh', 'invited priya.s@', '1h ago'],
                ['System', 'SSO policy updated', '3h ago'],
                ['Bill Ma', 'suspended Dan Kowalski', '3d ago'],
                ['Mina Klee', 'signed in from new device', '4d ago'],
              ].map(([who, what, when], i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '7px 0', borderBottom: i < 4 ? `1px dashed ${H.line}` : 'none', fontSize: 12 }}>
                  <span style={{ width: 5, height: 5, borderRadius: '50%', background: H.ink3 }}/>
                  <span><b style={{ fontWeight: 600 }}>{who}</b> <span style={{ color: H.ink2 }}>{what}</span></span>
                  <span style={{ flex: 1 }}/>
                  <span className="h-mono" style={{ fontSize: 11, color: H.ink3 }}>{when}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { HiLogin, HiITManagement });
