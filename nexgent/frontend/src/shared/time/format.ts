const formatter = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit"
});

export function formatClock(value: string) {
  return formatter.format(new Date(value));
}

export function formatRelative(value: string) {
  const then = new Date(value).getTime();
  const now = Date.now();
  const diffMinutes = Math.max(0, Math.round((now - then) / 60_000));

  if (diffMinutes < 1) {
    return "just now";
  }

  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }

  const hours = Math.floor(diffMinutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }

  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
