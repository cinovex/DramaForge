export function escapeMessageText(value: string): string {
  return value.replaceAll("'", "''").replaceAll("{", "'{'").replaceAll("}", "'}'");
}
