export interface CardTitle {
  title_id: string;
  serial_number: string;
  title: string;
  display_title?: string;
  media_type: string;
  genres?: string;
  year: number | null;
  poster_path: string | null;
}
