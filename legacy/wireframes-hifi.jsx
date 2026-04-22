// Hi-fi direction — polished professional look for JoineryFlow.
// Palette: neutral warm whites, single warm accent #c96442, Inter + JetBrains Mono.

const H = {
  bg: '#fbfaf7',
  surface: '#ffffff',
  surfaceAlt: '#f4f2ed',
  surfaceDeep: '#ece9e0',
  line: '#e4e0d8',
  line2: '#d0ccc2',
  ink: '#1b1a17',
  ink2: '#5a574f',
  ink3: '#8f8b80',
  ink4: '#b5b1a6',
  accent: '#c96442',
  accentDeep: '#a84f31',
  accentSoft: '#f3e0d6',
  good: '#3f7d48',
  goodSoft: '#e2efdf',
  warn: '#c48a2e',
  warnSoft: '#f4e7cf',
  bad: '#b4443d',
  badSoft: '#f2dcd9',
  info: '#3d6b8a',
  infoSoft: '#dce6ed',
  font: '"Inter", -apple-system, BlinkMacSystemFont, sans-serif',
  mono: '"JetBrains Mono", ui-monospace, monospace',
};

if (typeof document !== 'undefined' && !document.getElementById('h-styles')) {
  // ensure inter + jetbrains mono
  if (!document.getElementById('h-fonts')) {
    const l = document.createElement('link');
    l.id = 'h-fonts';
    l.rel = 'stylesheet';
    l.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap';
    document.head.appendChild(l);
  }
  const s = document.createElement('style');
  s.id = 'h-styles';
  s.textContent = `
    .h-root { font-family: ${H.font}; color: ${H.ink}; background: ${H.bg}; font-feature-settings: "cv11","ss01"; }
    .h-root * { box-sizing: border-box; }
    .h-mono { font-family: ${H.mono}; font-feature-settings: "tnum"; }
    .h-btn { border: 1px solid ${H.line2}; padding: 5px 10px; border-radius: 5px; background: ${H.surface}; font-size: 12px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 5px; color: ${H.ink}; font-family: inherit; line-height: 1; white-space: nowrap; }
    .h-btn:hover { background: ${H.surfaceAlt}; }
    .h-btn-primary { background: ${H.ink}; color: ${H.surface}; border-color: ${H.ink}; }
    .h-btn-primary:hover { background: #333; }
    .h-btn-accent { background: ${H.accent}; color: #fff; border-color: ${H.accent}; }
    .h-btn-accent:hover { background: ${H.accentDeep}; }
    .h-btn-ghost { border: 1px solid transparent; background: transparent; }
    .h-btn-ghost:hover { background: ${H.surfaceAlt}; }
    .h-pill { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; background: ${H.surfaceAlt}; color: ${H.ink2}; border: 1px solid ${H.line}; line-height: 1.5; }
    .h-eyebrow { font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 600; color: ${H.ink3}; }
    .h-card { background: ${H.surface}; border: 1px solid ${H.line}; border-radius: 8px; }
    .h-row-hover:hover { background: ${H.surfaceAlt}; }
    .h-input { border: 1px solid ${H.line}; background: ${H.surface}; border-radius: 5px; padding: 5px 8px; font-size: 12px; font-family: inherit; color: ${H.ink}; outline: none; }
    .h-input:focus { border-color: ${H.accent}; }
    .h-subtab { padding: 6px 14px; font-size: 12px; font-weight: 500; color: ${H.ink2}; border-bottom: 2px solid transparent; cursor: pointer; white-space: nowrap; }
    .h-subtab-active { color: ${H.ink}; border-bottom-color: ${H.ink}; font-weight: 600; }
    .h-subtab:hover:not(.h-subtab-active) { color: ${H.ink}; }
  `;
  document.head.appendChild(s);
}

const HAvatar = ({ label, size = 24, color = H.accent }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: size, height: size, borderRadius: '50%', background: color, color: '#fff', fontSize: size * 0.38, fontWeight: 600, flexShrink: 0, fontFamily: H.font }}>{label}</span>
);

const HStatus = ({ s }) => {
  const map = {
    CLEAR: [H.good, H.goodSoft], APPROVED: [H.good, H.goodSoft], LIVE: [H.accent, H.accentSoft],
    HOLD: [H.warn, H.warnSoft], 'NOTE!': [H.warn, H.warnSoft], SUBMITTED: [H.info, H.infoSoft],
    VOID: [H.bad, H.badSoft], REJECTED: [H.bad, H.badSoft], RTO: [H.accent, H.accentSoft],
    ORDERED: [H.info, H.infoSoft], OVERDUE: [H.bad, H.badSoft], ARRIVED: [H.good, H.goodSoft],
    NEXT: [H.accent, H.accentSoft], TBC: [H.ink2, H.surfaceAlt],
  };
  const [fg, bg] = map[s] || [H.ink2, H.surfaceAlt];
  return <span style={{ display: 'inline-block', padding: '1px 7px', borderRadius: 3, background: bg, color: fg, fontSize: 10, fontWeight: 600, letterSpacing: 0.04, border: `1px solid ${fg}22`, fontFamily: H.font }}>{s}</span>;
};

const HIcon = ({ d, size = 14, stroke = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke={stroke} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>{d}</svg>
);
const Icons = {
  search: <><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></>,
  plus: <path d="M8 3v10M3 8h10"/>,
  bell: <path d="M4.5 6.5a3.5 3.5 0 017 0v3l1 2H3.5l1-2z"/>,
  chev: <path d="M5 6l3 3 3-3"/>,
  chevR: <path d="M6 4l3 4-3 4"/>,
  filter: <path d="M2 3h12l-4.5 5.5V14L6.5 12V8.5z"/>,
  clock: <><circle cx="8" cy="8" r="5.5"/><path d="M8 5v3l2 1.5"/></>,
  box: <path d="M2 5l6-3 6 3v6l-6 3-6-3zM2 5l6 3 6-3M8 8v6"/>,
  cart: <path d="M2 2h2l1.5 9h8L15 5H5M6.5 13.5a1 1 0 110 2 1 1 0 010-2zm7 0a1 1 0 110 2 1 1 0 010-2z"/>,
  print: <path d="M4 6V2h8v4M4 12H2V7h12v5h-2M4 10h8v4H4z"/>,
  user: <><circle cx="8" cy="6" r="2.5"/><path d="M3 14c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5"/></>,
  settings: <><circle cx="8" cy="8" r="2"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4"/></>,
  upload: <path d="M8 2v8M4 6l4-4 4 4M2 12v2h12v-2"/>,
  download: <path d="M8 10V2M4 6l4 4 4-4M2 12v2h12v-2"/>,
  grid: <path d="M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z"/>,
  list: <path d="M2 3h12M2 8h12M2 13h12"/>,
  eye: <><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z"/><circle cx="8" cy="8" r="2"/></>,
  edit: <path d="M11 2l3 3-9 9H2v-3l9-9z"/>,
  x: <path d="M3 3l10 10M13 3L3 13"/>,
  menu: <path d="M2 4h12M2 8h12M2 12h12"/>,
  lock: <><rect x="3" y="7" width="10" height="7" rx="1"/><path d="M5 7V5a3 3 0 016 0v2"/></>,
  key: <><circle cx="5" cy="8" r="3"/><path d="M8 8h7M13 8v3M10.5 8v2"/></>,
  shield: <path d="M8 1l6 2v5c0 4-3 6-6 7-3-1-6-3-6-7V3z"/>,
  activity: <path d="M1 8h3l2-5 3 10 2-5h4"/>,
  project: <path d="M2 4a1 1 0 011-1h3l2 2h5a1 1 0 011 1v7a1 1 0 01-1 1H3a1 1 0 01-1-1z"/>,
  logout: <path d="M10 3h4v10h-4M8 5l3 3-3 3M11 8H2"/>,
  arrowU: <path d="M8 13V3M4 7l4-4 4 4"/>,
  arrowD: <path d="M8 3v10M4 9l4 4 4-4"/>,
  check: <path d="M3 8l3 3 7-7"/>,
  tag: <path d="M2 2h5l7 7-5 5-7-7z M5 5v.01"/>,
  users: <><circle cx="6" cy="6" r="2"/><circle cx="11" cy="7" r="1.8"/><path d="M2 13c0-2 2-3.5 4-3.5s4 1.5 4 3.5M10 12c.5-1.5 1.8-2.2 3-2.2s2.2.7 2.5 2"/></>,
  refresh: <path d="M2 8a6 6 0 0110-4.5L13 5M14 8a6 6 0 01-10 4.5L3 11M2 2v3h3M14 14v-3h-3"/>,
  import: <path d="M3 8h8M8 5l3 3-3 3M2 2h12v12H2z" />,
  room: <path d="M2 14V6l6-4 6 4v8H9v-5H7v5z"/>,
  dollar: <path d="M8 1v14M11 4H6.5a2 2 0 000 4h3a2 2 0 010 4H4"/>,
  history: <><circle cx="8" cy="8" r="6"/><path d="M8 4v4l2.5 2.5"/></>,
};

// Hi-fi app chrome with NEW tab sequence.
// active: top-level tab name
// subtabs: optional array of { key, label }
// activeSub: key of active subtab
// onSub: optional handler
const HAppChrome = ({ children, active = 'Dashboard', subtabs = null, activeSub = null, onSub = null, chromeExtra = null }) => {
  const tabs = ['Dashboard', 'Tracking', 'List', 'Orderbook', 'Shop Dwgs', 'iSample'];
  const projs = [
    ['Alfred Level 3 Fitout', '2273', true],
    ['Monash Uni FFT · Caulfield', '2351', false],
    ['Monash Uni FFT · Clayton', '2350', false],
    ['VSBA Mickleham Sec.', '2347', false],
    ['The Trentham', '2289', false],
    ['7SS Flinders West', '2255', false],
    ['Riverside Richmond', '2232', false],
  ];
  return (
    <div className="h-root" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* top bar */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '8px 14px', borderBottom: `1px solid ${H.line}`, background: H.surface, gap: 12, flexShrink: 0, height: 48 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 24, height: 24, borderRadius: 6, background: H.ink, display: 'flex', alignItems: 'center', justifyContent: 'center', color: H.bg, fontSize: 13, fontWeight: 700 }}>◴</div>
          <div style={{ fontSize: 14, fontWeight: 600, letterSpacing: -0.2 }}>Joinery<span style={{ color: H.accent }}>Flow</span></div>
        </div>
        <nav style={{ display: 'flex', gap: 2, marginLeft: 16 }}>
          {tabs.map(t => (
            <div key={t} style={{
              padding: '6px 12px', fontSize: 13, fontWeight: t === active ? 600 : 500,
              color: t === active ? H.ink : H.ink2, borderRadius: 5, cursor: 'pointer',
              background: t === active ? H.surfaceAlt : 'transparent',
            }}>{t}</div>
          ))}
        </nav>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px', border: `1px solid ${H.line}`, borderRadius: 6, background: H.bg, fontSize: 12, width: 240 }}>
          <HIcon d={Icons.search} size={12} stroke={H.ink3} />
          <span style={{ color: H.ink3 }}>Search · ⌘K</span>
        </div>
        <button className="h-btn h-btn-ghost" style={{ padding: 6 }}><HIcon d={Icons.bell} /></button>
        <HAvatar label="BM" size={28} />
      </div>
      {/* subtabs row, if any */}
      {subtabs && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 0, padding: '0 20px', borderBottom: `1px solid ${H.line}`, background: H.surface, flexShrink: 0 }}>
          {subtabs.map((t) => (
            <div key={t.key} onClick={() => onSub && onSub(t.key)}
              className={`h-subtab ${t.key === activeSub ? 'h-subtab-active' : ''}`}>
              {t.label}{t.count != null && <span style={{ color: H.ink3, marginLeft: 6, fontWeight: 500 }}>{t.count}</span>}
            </div>
          ))}
          <div style={{ flex: 1 }} />
          {chromeExtra}
        </div>
      )}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* left sidebar */}
        <div style={{ width: 220, background: H.surface, borderRight: `1px solid ${H.line}`, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
          <div style={{ padding: '12px 12px 6px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="h-eyebrow">Projects</span>
            <button className="h-btn h-btn-ghost" style={{ padding: 2 }}><HIcon d={Icons.plus} size={11}/></button>
          </div>
          <div style={{ padding: '0 10px 8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '4px 8px', border: `1px solid ${H.line}`, borderRadius: 5, background: H.bg }}>
              <HIcon d={Icons.search} size={11} stroke={H.ink3} />
              <span style={{ fontSize: 12, color: H.ink3 }}>filter…</span>
            </div>
          </div>
          <div style={{ overflow: 'auto', flex: 1, padding: '0 6px 10px' }}>
            {projs.map(([n, pid, on]) => (
              <div key={pid} style={{
                padding: '6px 8px', borderRadius: 5, marginBottom: 1, cursor: 'pointer',
                background: on ? H.surfaceAlt : 'transparent',
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <div style={{ width: 3, height: 14, borderRadius: 2, background: on ? H.accent : 'transparent' }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: on ? 600 : 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n}</div>
                  <div className="h-mono" style={{ fontSize: 10, color: H.ink3 }}>#{pid}</div>
                </div>
              </div>
            ))}
          </div>
          <div style={{ padding: '8px 10px', borderTop: `1px solid ${H.line}`, display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: H.ink3 }}>
            <HAvatar label="BM" size={22}/>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 500, color: H.ink }}>Bill Ma</div>
              <div>Estimator</div>
            </div>
            <HIcon d={Icons.settings} size={13} stroke={H.ink3}/>
          </div>
        </div>
        <div style={{ flex: 1, overflow: 'hidden', minWidth: 0, background: H.bg }}>{children}</div>
      </div>
    </div>
  );
};

Object.assign(window, { H, HAvatar, HStatus, HIcon, Icons, HAppChrome });
