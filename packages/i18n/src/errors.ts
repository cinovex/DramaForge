import { IntlMessageFormat } from "intl-messageformat";
import type { MessageDescriptor } from "./index";

export function messageError(message: MessageDescriptor, options?: ErrorOptions): Error & { i18nMessage: MessageDescriptor } {
  const text = message.values
    ? String(new IntlMessageFormat(message.id, "zh-CN", undefined, { ignoreTag: true }).format(Object.fromEntries(
      Object.entries(message.values).map(([key, value]) => [key, typeof value === "number" || value instanceof Date ? value : String(value)]),
    )))
    : message.id;
  return Object.assign(new Error(text, options), { i18nMessage: message });
}
