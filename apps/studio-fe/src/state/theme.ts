export type ThemeId =
  | "cobweb" | "violet" | "amber" | "arctic"
  | "noir" | "neon" | "frosted" | "brutalist" | "warm" | "metal";

export interface ThemeDef {
  id: ThemeId;
  label: string;
  dot: string;
  group: "color" | "style";
}

export const THEMES: ThemeDef[] = [
  // Color themes
  { id: "cobweb", label: "Cobweb Teal", dot: "bg-cyan-400", group: "color" },
  { id: "violet", label: "Violet Haze", dot: "bg-violet-400", group: "color" },
  { id: "amber", label: "Amber Forge", dot: "bg-amber-400", group: "color" },
  { id: "arctic", label: "Arctic Blue", dot: "bg-indigo-400", group: "color" },
  // Style themes
  { id: "noir", label: "Midnight Noir", dot: "bg-red-500", group: "style" },
  { id: "neon", label: "Neon Terminal", dot: "bg-green-400", group: "style" },
  { id: "frosted", label: "Frosted Aurora", dot: "bg-pink-400", group: "style" },
  { id: "brutalist", label: "Brutalist", dot: "bg-white", group: "style" },
  { id: "warm", label: "Warm Parchment", dot: "bg-orange-300", group: "style" },
  { id: "metal", label: "Frosted Metal", dot: "bg-slate-400", group: "style" },
];

const STORAGE_KEY = "theridion.theme";

export function loadTheme(): ThemeId {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && THEMES.some((t) => t.id === stored)) return stored as ThemeId;
  return "cobweb";
}

export function applyTheme(id: ThemeId): void {
  const html = document.documentElement;
  for (const t of THEMES) html.classList.remove(`theme-${t.id}`);
  html.classList.add(`theme-${id}`);
  localStorage.setItem(STORAGE_KEY, id);
}
