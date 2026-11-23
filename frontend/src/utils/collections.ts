export function uniqueByTitleId<T extends { title_id: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.title_id)) {
      return false;
    }
    seen.add(item.title_id);
    return true;
  });
}
