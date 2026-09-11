const DAY_MS = 24 * 60 * 60 * 1000;

export function parseIsoDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day, 12, 0, 0, 0);
}

export function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function startOfWeek(value: Date): Date {
  const result = new Date(value.getFullYear(), value.getMonth(), value.getDate(), 12);
  const day = result.getDay();
  const offset = day === 0 ? -6 : 1 - day;
  result.setDate(result.getDate() + offset);
  return result;
}

export function addDays(value: Date, days: number): Date {
  const result = new Date(value.getTime());
  result.setDate(result.getDate() + days);
  return result;
}

export function weekDays(monday: Date): Date[] {
  return Array.from({ length: 7 }, (_, index) => addDays(monday, index));
}

export function sameIsoDate(left: string, right: Date): boolean {
  return left === toIsoDate(right);
}

export function formatDay(value: Date): string {
  const label = new Intl.DateTimeFormat("fr-CA", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(value);
  return label.replace(".", "");
}

export function formatWeekRange(monday: Date): string {
  const sunday = addDays(monday, 6);
  const formatter = new Intl.DateTimeFormat("fr-CA", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return `${formatter.format(monday)} — ${formatter.format(sunday)}`;
}

export function isToday(value: Date): boolean {
  const now = new Date();
  return (
    value.getFullYear() === now.getFullYear()
    && value.getMonth() === now.getMonth()
    && value.getDate() === now.getDate()
  );
}

export function dayDistance(left: Date, right: Date): number {
  return Math.round((right.getTime() - left.getTime()) / DAY_MS);
}
