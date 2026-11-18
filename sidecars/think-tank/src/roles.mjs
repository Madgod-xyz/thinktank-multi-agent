export const CANONICAL_ROLES = [
  {
    id: 'main_agent', monogram: 'MA', frameShape: 'hexagon', tier: 'coordinator', tierRow: 1, colIndex: 0,
    canInterrogate: true, canPeerSync: true,
    title: { fa: 'عامل اصلی', en: 'Main Agent' },
    shortTitle: { fa: 'عامل اصلی', en: 'Main Agent' },
    specialty: { fa: 'هماهنگی کل، غربالگری و تحویل نهایی', en: 'Triage, orchestration, and final delivery' },
    skills: ['think-room', 'task-orchestration', 'quality-gate', 'ponytail'],
    glyph: 'M8 1.5l5.5 3.2v6.6L8 14.5l-5.5-3.2V4.7L8 1.5z',
  },
  {
    id: 'team-manager', monogram: 'TM', frameShape: 'square', tier: 'supervisor', tierRow: 1, colIndex: 1,
    canInterrogate: true, canPeerSync: true,
    title: { fa: 'مدیر تیم و سرگروه هماهنگی', en: 'Team Manager' },
    shortTitle: { fa: 'مدیر تیم WBS', en: 'Team Manager' },
    specialty: { fa: 'تقسیم کار WBS و بازخواست پیشرفت', en: 'WBS breakdown, locks, and progress tracking' },
    skills: ['task-orchestration', 'think-room', 'requirements-traceability', 'ponytail'],
    glyph: 'M2.5 3.5h11v3h-11zM2.5 9.5h4.5v3H2.5zM9 9.5h4.5v3H9z',
  },
  {
    id: 'council-critic', monogram: 'CC', frameShape: 'square', tier: 'supervisor', tierRow: 1, colIndex: 2,
    canInterrogate: true, canPeerSync: true,
    title: { fa: 'نقاد و منتقد شورا', en: 'Council Critic' },
    shortTitle: { fa: 'نقاد شورا', en: 'Council Critic' },
    specialty: { fa: 'شکار ایرادات کد، معماری و پروسه', en: 'Defect hunting, security, and anti-slop critique' },
    skills: ['think-room', 'quality-gate', 'evidence-verification', 'ponytail'],
    glyph: 'M8 2l6 11H2L8 2zm0 4v3.5m0 2v.5',
  },
  {
    id: 'code-reviewer', monogram: 'CR', frameShape: 'square', tier: 'supervisor', tierRow: 1, colIndex: 3,
    canInterrogate: true, canPeerSync: true,
    title: { fa: 'کد ریویور ارشد و فرمانده تست', en: 'Code Reviewer' },
    shortTitle: { fa: 'کد ریویور ارشد', en: 'Code Reviewer' },
    specialty: { fa: 'بررسی خط‌به‌خط کدها و هدایت تستر QA', en: 'Line-by-line review and QA command' },
    skills: ['backend-quality', 'frontend-quality', 'quality-gate', 'hallmark', 'ponytail'],
    glyph: 'M5.5 4.5L2 8l3.5 3.5M10.5 4.5L14 8l-3.5 3.5M8.8 3l-1.6 10',
  },
  {
    id: 'qa-reviewer', monogram: 'QA', frameShape: 'diamond', tier: 'tester', tierRow: 2, colIndex: 3,
    reportsTo: 'code-reviewer', canInterrogate: false, canPeerSync: true,
    title: { fa: 'تستر و آزمون‌گر QA', en: 'QA Reviewer' },
    shortTitle: { fa: 'آزمون‌گر QA', en: 'QA Reviewer' },
    specialty: { fa: 'اجرای تست‌های عملی با مدرک اجرایی', en: 'Evidence-backed unit, contract, and UI tests' },
    skills: ['quality-gate', 'browser-check', 'accessibility-qa', 'ponytail'],
    glyph: 'M8 1.8l6.2 6.2L8 14.2 1.8 8 8 1.8zm-2.3 6.2l1.6 1.6 3.2-3.2',
  },
  {
    id: 'ui-frontend-designer', monogram: 'UI', frameShape: 'circle', tier: 'worker', tierRow: 3, colIndex: 0,
    canInterrogate: false, canPeerSync: true,
    title: { fa: 'متخصص UI، دیزاین و فرانت‌اند', en: 'UI and Frontend Architect' },
    shortTitle: { fa: 'طراح UI و فرانت', en: 'UI Architect' },
    specialty: { fa: 'دیزاین سیستم، RTL/فارسی و ضد AI Slop', en: 'Design tokens, RTL craft, and Hallmark compliance' },
    skills: ['hallmark', 'design-tokens', 'responsive-layout', 'accessibility-qa', 'ponytail'],
    glyph: 'M2.5 3.5h11v9h-11zM2.5 6.5h11M6 6.5v6',
  },
  {
    id: 'backend-auditor', monogram: 'BE', frameShape: 'circle', tier: 'worker', tierRow: 3, colIndex: 1,
    canInterrogate: false, canPeerSync: true,
    title: { fa: 'متخصص بک‌اند و کدهای هسته', en: 'Backend and Core Engineer' },
    shortTitle: { fa: 'مهندس بک‌اند', en: 'Backend Engineer' },
    specialty: { fa: 'معماری سرور، API، دیتابیس و امنیت', en: 'APIs, SQLite WAL, security, and core logic' },
    skills: ['engineering-director', 'backend-quality', 'firebase-master', 'ponytail'],
    glyph: 'M3 3.5h10v3H3zM3 9.5h10v3H3zM5 5h.01M5 11h.01',
  },
  {
    id: 'ecommerce_seo_operator', monogram: 'SE', frameShape: 'circle', tier: 'worker', tierRow: 3, colIndex: 2,
    canInterrogate: false, canPeerSync: true,
    title: { fa: 'متخصص سئو و SEO محصولات', en: 'E-Commerce SEO Specialist' },
    shortTitle: { fa: 'متخصص سئو', en: 'SEO Specialist' },
    specialty: { fa: 'سئوی تکنیکال، اسکیما و کپی‌رایتینگ', en: 'Technical SEO, Schema, and product copy' },
    skills: ['perfume-ecommerce-seo', 'wp-seo-content-engine', 'woo-ecommerce-director'],
    glyph: 'M7 2.8a4.2 4.2 0 1 0 0 8.4 4.2 4.2 0 0 0 0-8.4zM10.2 10.2l3 3',
  },
  {
    id: 'wp_technical_operator', monogram: 'WP', frameShape: 'circle', tier: 'worker', tierRow: 3, colIndex: 3,
    canInterrogate: false, canPeerSync: true,
    title: { fa: 'متخصص ووکامرس و وردپرس', en: 'WP and WooCommerce SRE' },
    shortTitle: { fa: 'مهندس ووکامرس', en: 'WP SRE' },
    specialty: { fa: 'SRE وردپرس، دیتابیس، ردیس و کاتالوگ', en: 'WordPress SRE, Redis, MySQL, and store ops' },
    skills: ['wp-technical-ops-sre', 'woo-ecommerce-director', 'wp-commerce-ops', 'ponytail'],
    glyph: 'M8 2.2a5.8 5.8 0 1 0 0 11.6A5.8 5.8 0 0 0 8 2.2zM5.2 5.5l1.8 5 1-3 1 3 1.8-5',
  },
];

const ROLE_BY_ID = new Map(CANONICAL_ROLES.map((r) => [r.id, r]));

export const ROLE_ALIAS_MAP = {
  main: 'main_agent', root: 'main_agent', coordinator: 'main_agent', orchestrator: 'main_agent',
  'main-agent': 'main_agent', main_agent: 'main_agent', antigravity: 'main_agent', 'عامل اصلی': 'main_agent',
  manager: 'team-manager', 'team-manager': 'team-manager', team_manager: 'team-manager',
  'council-architect': 'team-manager', council_architect: 'team-manager',
  'requirements-auditor': 'team-manager', 'context-memory-curator': 'team-manager',
  'data-intelligence-curator': 'team-manager', 'performance-cost-analyst': 'team-manager',
  'skill-coach': 'team-manager', 'مدیر تیم': 'team-manager',
  critic: 'council-critic', 'council-critic': 'council-critic', council_critic: 'council-critic',
  'evidence-critical-reviewer': 'council-critic', 'agent-evaluator': 'council-critic', 'نقاد شورا': 'council-critic',
  reviewer: 'code-reviewer', 'code-reviewer': 'code-reviewer', code_reviewer: 'code-reviewer',
  'integration-reviewer': 'code-reviewer', integration_reviewer: 'code-reviewer',
  security_reviewer: 'code-reviewer', 'کد ریویور': 'code-reviewer',
  qa: 'qa-reviewer', 'qa-reviewer': 'qa-reviewer', qa_reviewer: 'qa-reviewer',
  tester: 'qa-reviewer', 'visual-qa': 'qa-reviewer', flutter_a11y_agent: 'qa-reviewer', 'تستر qa': 'qa-reviewer',
  designer: 'ui-frontend-designer', 'ui-frontend-designer': 'ui-frontend-designer',
  designer_solver: 'ui-frontend-designer', ui_frontend_designer: 'ui-frontend-designer',
  'motion-director': 'ui-frontend-designer', 'طراح رابط': 'ui-frontend-designer',
  backend: 'backend-auditor', 'backend-auditor': 'backend-auditor', backend_auditor: 'backend-auditor',
  backend_engineer: 'backend-auditor', implementer: 'backend-auditor',
  'deep-researcher': 'backend-auditor', 'research-scout': 'backend-auditor', 'متخصص بک‌اند': 'backend-auditor',
  seo: 'ecommerce_seo_operator', ecommerce_seo_operator: 'ecommerce_seo_operator',
  seo_specialist: 'ecommerce_seo_operator', 'ecommerce-seo-operator': 'ecommerce_seo_operator', 'متخصص سئو': 'ecommerce_seo_operator',
  wp: 'wp_technical_operator', wp_technical_operator: 'wp_technical_operator',
  wordpress: 'wp_technical_operator', woocommerce: 'wp_technical_operator',
  'wp-technical-operator': 'wp_technical_operator', 'متخصص ووکامرس': 'wp_technical_operator',
  user: 'user', operator: 'user', human: 'user', owner: 'user', usr: 'user', 'کاربر': 'user', 'شما': 'user',
  all: 'all', broadcast: 'all', team: 'all', 'همه': 'all',
};

export function normalizeRoleId(raw) {
  if (!raw || typeof raw !== 'string') return '';
  let clean = raw.toLowerCase().trim();
  clean = clean.replace(/^(?:(?:agent|tt)[_-])+/, '');
  if (ROLE_ALIAS_MAP[clean]) return ROLE_ALIAS_MAP[clean];
  if (ROLE_BY_ID.has(clean)) return clean;
  const dashed = clean.replace(/_/g, '-');
  if (ROLE_ALIAS_MAP[dashed]) return ROLE_ALIAS_MAP[dashed];
  if (ROLE_BY_ID.has(dashed)) return dashed;
  const underscored = clean.replace(/-/g, '_');
  if (ROLE_ALIAS_MAP[underscored]) return ROLE_ALIAS_MAP[underscored];
  if (ROLE_BY_ID.has(underscored)) return underscored;
  return clean;
}

export function getRoleMeta(raw) {
  const id = normalizeRoleId(raw);
  if (id === 'user') {
    return {
      id: 'user', monogram: 'YOU', frameShape: 'circle', tier: 'user', tierRow: 0,
      title: { fa: 'شما', en: 'You' }, shortTitle: { fa: 'شما', en: 'You' },
      specialty: { fa: 'هدایتگر پرونده', en: 'Case Owner' }, skills: [],
      glyph: 'M8 3.2a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8zM3.5 13c.6-2.2 2.4-3.4 4.5-3.4s3.9 1.2 4.5 3.4',
    };
  }
  return ROLE_BY_ID.get(id) || null;
}

export function roleTitle(raw, lang = 'fa', short = false) {
  const meta = getRoleMeta(raw);
  const loc = String(lang || 'fa').toLowerCase().startsWith('en') ? 'en' : 'fa';
  if (!meta) return String(raw || '-');
  return (short ? meta.shortTitle?.[loc] : meta.title?.[loc]) || meta.title?.en || meta.id;
}

export function roleMonogram(raw) {
  const meta = getRoleMeta(raw);
  if (meta) return meta.monogram;
  const s = String(raw || '').replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
  return s.slice(0, 2) || 'AG';
}
