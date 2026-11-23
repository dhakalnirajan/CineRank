export interface TitleRouteIdentity {
  media_type: string;
  serial_number: string;
}

export function getTitleUrl(title: TitleRouteIdentity): string {
  if (title.media_type !== "movie" && title.media_type !== "tv") {
    throw new Error(`Unsupported media type: ${title.media_type}`);
  }
  if (!/^\d{6,}$/.test(title.serial_number)) {
    throw new Error("Invalid title serial number");
  }
  return `/${title.media_type}/${title.serial_number}/`;
}
