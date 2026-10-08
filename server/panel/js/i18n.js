const translations = {
  en: {
    tagline: 'Game Tunneling Platform',
    signin_title: 'Sign in',
    signin_sub: 'Access your tunnel dashboard.',
    email: 'Email',
    password: 'Password',
    signin: 'Sign In',
    create_account: 'Create account',
    have_account: 'Already have an account?',
    view_github: 'View on GitHub',
    nav_dashboard: 'Dashboard',
    nav_tunnels: 'Tunnels',
    nav_create: 'Create Tunnel',
    nav_activity: 'Activity',
    nav_settings: 'Settings',
    network_operational: 'Network Operational',
    greeting: 'Hello',
    dashboard_sub: 'Manage your game tunnels and monitor your network.',
    active_tunnels: 'Active Tunnels',
    online_connections: 'Online Connections',
    bandwidth: 'Bandwidth',
    uptime: 'Uptime',
    recent_tunnels: 'Recent Tunnels',
    view_all: 'View all',
    tunnels_sub: 'All your game tunnels in one place.',
    tunnel_name: 'Tunnel Name',
    game: 'Game',
    protocol: 'Protocol',
    local_host: 'Local Host',
    local_port: 'Local Port',
    create: 'Create Tunnel',
    no_tunnels: 'No tunnels yet. Create your first game tunnel.',
    appearance: 'Appearance',
    language: 'Language',
    theme_dark: 'Dark',
    theme_light: 'Light',
    theme_system: 'System',
    copy: 'Copy',
    delete: 'Delete',
    confirm_delete: 'Delete this tunnel?',
    status_online: 'ONLINE',
    status_offline: 'OFFLINE',
  },
  fa: {
    tagline: 'پلتفرم تونل بازی',
    signin_title: 'ورود',
    signin_sub: 'به داشبورد تونل‌های خود دسترسی پیدا کنید.',
    email: 'ایمیل',
    password: 'رمز عبور',
    signin: 'ورود',
    create_account: 'ساخت حساب',
    have_account: 'حساب دارید؟',
    view_github: 'مشاهده در گیت‌هاب',
    nav_dashboard: 'داشبورد',
    nav_tunnels: 'تونل‌ها',
    nav_create: 'ساخت تونل',
    nav_activity: 'فعالیت',
    nav_settings: 'تنظیمات',
    network_operational: 'شبکه فعال',
    greeting: 'سلام',
    dashboard_sub: 'تونل‌های بازی خود را مدیریت و شبکه را مانیتور کنید.',
    active_tunnels: 'تونل‌های فعال',
    online_connections: 'اتصالات آنلاین',
    bandwidth: 'پهنای باند',
    uptime: 'زمان کارکرد',
    recent_tunnels: 'تونل‌های اخیر',
    view_all: 'مشاهده همه',
    tunnels_sub: 'تمام تونل‌های بازی شما در یک جا.',
    tunnel_name: 'نام تونل',
    game: 'بازی',
    protocol: 'پروتکل',
    local_host: 'هاست محلی',
    local_port: 'پورت محلی',
    create: 'ساخت تونل',
    no_tunnels: 'هنوز تونلی ندارید. اولین تونل بازی خود را بسازید.',
    appearance: 'ظاهر',
    language: 'زبان',
    theme_dark: 'تیره',
    theme_light: 'روشن',
    theme_system: 'سیستم',
    copy: 'کپی',
    delete: 'حذف',
    confirm_delete: 'این تونل حذف شود؟',
    status_online: 'آنلاین',
    status_offline: 'آفلاین',
  },
};

const I18N = {
  current: 'en',
  init() {
    const saved = localStorage.getItem('lanvexa.lang') || 'en';
    this.set(saved);
  },
  set(lang) {
    this.current = lang;
    localStorage.setItem('lanvexa.lang', lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr';

    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      const text = translations[lang][key];
      if (text) el.textContent = text;
    });
  },
  t(key) {
    return translations[this.current][key] || key;
  },
};

I18N.init();