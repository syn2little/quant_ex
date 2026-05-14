import { useTranslation } from 'react-i18next';
import { clsx } from 'clsx';

export function LanguageToggle() {
  const { i18n } = useTranslation();

  const toggle = (lang: string) => {
    i18n.changeLanguage(lang).catch(console.error);
    localStorage.setItem('lang', lang);
  };

  return (
    <div className="flex border-t border-[#20342c] bg-[#0e1713]">
      {(['en', 'zh'] as const).map((lang) => (
        <button
          key={lang}
          onClick={() => toggle(lang)}
          className={clsx(
            "flex-1 py-2 text-[10px] font-mono font-medium uppercase tracking-wider transition-colors",
            i18n.language === lang
              ? "bg-[#1b3028] text-[#78ddb0]"
              : "text-[#8ca59a] hover:text-[#eef6f1]"
          )}
        >
          {lang === 'zh' ? '中' : 'EN'}
        </button>
      ))}
    </div>
  );
}
