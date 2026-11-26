import en from "./en";
import de from "./de";
export type Lang = "en" | "de";
export const dicts = { en, de };
export const t = (lang: Lang) => dicts[lang];
export const other = (lang: Lang): Lang => (lang === "en" ? "de" : "en");
// Rechtliche Unterseiten heißen je Sprache anders
export const policyPath = (lang: Lang) => (lang === "en" ? "/en/privacy/" : "/de/datenschutz/");
