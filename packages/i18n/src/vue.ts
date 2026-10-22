import { shallowRef } from "vue";
import * as core from "./index";
export { supportedLocales, normalizeLocale, detectLocale, msg } from "./index";
export type { Locale, MessageDescriptor } from "./index";

export const locale = shallowRef<core.Locale>(core.getLocale());
core.subscribeLocale(value => { locale.value = value; });
export function setLocale(value: core.Locale) { core.setLocale(value); }
export function translate(message: string | core.MessageDescriptor, values?: Record<string, unknown>) {
  return core.translate(message, values, locale.value);
}
export function t(strings: TemplateStringsArray, ...values: unknown[]) {
  return translate(core.msg(strings, ...values));
}
