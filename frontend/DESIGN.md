# CineRank Frontend Design System

Current as of the Netflix-inspired cinematic redesign.

## 1. Visual direction

CineRank uses a dark cinematic canvas with a warm red accent, crisp white editorial type, and restrained gradient depth. The goal is a premium movie-rental-store feel rather than a dashboard feel. Surfaces are dark, borders are subtle, and interaction accents are concentrated in orange/red and gentle slate highlights.

## 2. Color tokens

Default accent:

- `--color-accent: #e50914`

Surface family:

- Page canvas is near-black.
- Navbar uses a solid dark surface when scrolled, and a translucent gradient over the home hero.
- Footer uses the site’s near-black footer tone with a subtle top border.
- Cards, panels, and popovers use dark zinc-leaning surfaces with low-opacity highlights on hover.

Text family:

- Primary on-dark text is white or near-white.
- Secondary and muted text uses white/60 to white/30 ranges.
- Accent text uses the orange family for small emphasis, such as ratings.

## 3. Typography

Fonts:

- Display and editorial type uses the site’s display font token.
- UI/body text uses the site’s sans token.
- Tabular numeric values use tabular styling where appropriate.

Scale and priorities:

- Headlines are large, tight, and high-contrast.
- Nav items use a compact medium weight.
- Metadata uses a small, calm secondary style.
- Ratings and years get subtle tabular emphasis without becoming noisy.

No em dashes, en dashes, or middle dots are used in UI copy. Hyphens, commas, colons, and periods are used instead.

## 4. Spacing system

- Page layout is constrained by `.page-shell`, which centers content with responsive inline padding and a maximum width.
- Navbar height is `var(--header-height)` (72px).
- Footer uses generous vertical rhythm: wide top padding, clear bottom strip, and a divider between zones.
- Compact navbar search uses a smaller input height than page-level search.
- Poster thumbnails in the navbar popover use a fixed compact size.
- The rails, cards, hero, and footer each use their own section rhythm, but all share the same underlying spacing tokens.

## 5. Layout patterns

### 5.1 Page shell

`.page-shell` is the main constrained layout wrapper. Most pages center their content inside it. Full-bleed visuals such as the home hero break out of the shell intentionally.

### 5.2 Navbar layout

Three-zone horizontal layout:

1. Brand + primary nav left.
2. Compact search center, flex-1 with a max width.
3. Auth controls right, flush to the edge.

The navbar is `z-50` and fixed on every route. It is translucent over the home hero and solid everywhere else. `AppShell` and `AuthLayout` render the same `Header`, so login and register match the rest of the app.

The left brand/nav group and the right auth group are `shrink-0`. The search zone is flex-1 with a capped width, and the right group reserves a minimum width on desktop so the search field stays put when auth changes.

The mobile bottom navigation adapts its equal-width slot count to the visible destinations. Signed-out users see one `Sign in` destination instead of protected destinations; signed-in users see both `For you` and `Watchlist`.

### 5.3 Footer layout

Two-zone grid:

- Left: constrained brand area with logo, tagline, and attribution.
- Right: EXPLORE and COMMUNITY columns.
- Bottom strip: copyright line with a top divider.
- EXPLORE and COMMUNITY link groups use a warm orange hover treatment.

## 6. Navbar and search patterns

### 6.1 Brand

The Logo component renders the compact brand mark in the navbar and the fuller wordmark where needed. It is the only brand element in the header.

### 6.2 Primary nav

Primary nav items are defined in `navItems.ts`. They render as text links with an underline indicator on the active route. `For you` and `Watchlist` are auth-gated; the catalogue and search destinations are public.

### 6.3 Navbar search

Navbar search is a compact database search input that opens a modal result dialog.

Rules:

- One leading magnifying-glass icon and one internal clear button.
- The field remains available on every route and auth state.
- Input is debounced before the backend search request. Enter opens the active result or the full search route.
- A dim backdrop sits below the fixed navbar; the result panel is centered below the navbar with a bounded height.
- Result rows show normalized title, separate release year, primary genre/type and poster artwork when available. Raw database IDs are never rendered.
- Results link to the title detail page; a full-results action opens the dedicated search route.

### 6.4 Modal states

- Loading: branded dark skeleton rows with fixed poster dimensions.
- Empty: explicit no-match message.
- Error: non-technical failure message.
- Results: poster thumbnail, normalized title, genre/type and year.

### 6.5 Keyboard and dismissal

- Up/Down moves the active result.
- Enter opens the active result or the full search route.
- Escape closes the dialog and blurs the search field.
- Clicking the backdrop or close control closes the dialog.

### 6.6 Poster fallback

When artwork is missing, the navbar uses a deterministic typographic fallback:

- Dark red-to-amber gradient tile.
- Compact two-letter-ish initials.
- No ID-derived or title-leaking fallback text.

## 7. Avatar and signed-in identity pattern

Signed-in identity is a compact account control, not an inline profile pill:

- A `36px` circular avatar button with a 50 percent border radius.
- A generic person icon on a deep red gradient with a subtle white ring. No initials and no visible username in the navbar.
- The username lives inside the dropdown, keeping branding and identity visually separate.
- The avatar sits in a `relative` wrapper. The menu is absolutely positioned below it, so the header height and search width never change.
- Click, Enter, or Space toggles the menu. Hover does not open or close it, and moving the pointer away leaves it open until another click, an outside press, Escape, or a route change.
- The menu shows username and email, then Profile, Watchlist, Rating history, and Sign out.
- Escape closes the menu and restores focus to the avatar.
- The panel begins immediately below the avatar with internal top padding, giving it visual separation without a layout gap.
- The Profile route contains identity editing, avatar upload, account statistics and session security controls.

Signed-out controls:

- “Sign in” ghost button.
- “Join CineRank” primary button.

Auth states are handled explicitly. Search stays visible for every status; loading and unresolved sessions keep the right-hand zone at a stable width with a small pulsing placeholder.

## 8. Footer pattern

Footer structure:

- `.page-shell`-aligned container.
- Background tone is near-black with a subtle top border.
- Top section: responsive grid with brand, Explore, Community, and Legal and Attribution columns.
- Legal and Attribution carries the artwork and metadata credit instead of the brand tagline.
- Bottom strip: copyright line separated by a divider from the upper footer.
- Copyright strip is left-aligned and not gated behind login.

Content rules:

- No filler copy.
- No auth-gated copyright.
- EXPLORE and COMMUNITY link groups use a warm orange hover treatment.
- Links are purposeful and scan quickly.

## 9. Card and media pattern

- Media cards use a 2:3 poster frame.
- Missing artwork uses a deterministic typographic poster rather than a broken-image icon.
- Watchlist and selection actions appear on hover where appropriate.
- Genre and metadata are separated visually, not mushed into one separator-delimited string.

### 9.1 Horizontal rails

- The scroller owns `overflow-x: auto`, has no horizontal padding or negative margins, and uses `snap-x`.
- Edge fades come from `mask-image` on the scroller itself: transparent at 0 percent and 100 percent, opaque from 5 percent to 95 percent. No full-height gradient overlay is placed over the rail.
- Each card wrapper declares an explicit width and `shrink-0`, so cards never collapse or resize during scroll.
- The scroller keeps small vertical padding so hover scaling, poster shadows and focus outlines are not clipped. It uses `gap-5` on narrow screens and a wider gap at desktop breakpoints.
- Previous and next controls float above the rail on desktop without a background strip, so they cannot create a visible vertical edge.

### 9.2 Profile gallery cards

- Rating history and watchlist entries use the same card family: rounded dark surface, thin border, and a 2:3 poster frame.
- Titles use the card title token and the strongest text weight in the card. Dates sit below in the muted meta token.
- Rating cards place a compact star badge over the artwork. Watchlist cards use the saved date as their meta line.
- Genre remains a separate chip below the date. Year and date are never joined into a separator-delimited string.
- Cards lift by 2px, brighten their border, and scale the artwork slightly on hover.
- The gallery grid is two columns on small screens, then three, four, and five columns at wider breakpoints.
- History cards use the standard typographic artwork fallback because history responses do not include poster paths.

### 9.3 Title-derived cover shapes

Every poster carries a four-layer abstract polygon composition computed from its title. The same title always renders the same art, and different titles render different compositions.

- The seed is the normalized display title plus release year, so remakes with identical names still diverge.
- A deterministic FNV-1a hash with an avalanche mix feeds separate bit windows for polygon geometry, position, size, rotation, tone and motion. A seeded Mulberry32 stream builds each silhouette.
- Every layer is an irregular polygon with 3 to 10 sides. Vertex angles receive a bounded jitter and every vertex gets its own radius, so adjacent sides have unequal lengths without self-intersection.
- Each layer is independently positioned, sized, rotated, toned and motion-timed. Tones are ember, amber, bone and steel.
- Positions stay inside 15 to 85 percent of the cover. Polygon radii stay within the 100 x 100 view box, so no silhouette is clipped away.
- Layer opacity stays low. Screen blending plus soft blur makes overlaps merge into brighter fluid areas and separate as the layers move apart.
- Typographic fallbacks render the composition boldly behind the title block. Real artwork receives the same composition at reduced opacity with a screen blend and a bottom shade, keeping the photograph readable.
- The composition is decorative and hidden from assistive technology. Titles and metadata remain the accessible content.
- Cards keep the shared 2:3 frame so grids and rails stay aligned. Individuality comes from the shape composition, not from inconsistent card geometry.

### 9.4 Living shape motion

Shapes are deliberately fluid and energetic. There is no physics simulation and no JavaScript animation loop.

- Each layer enters with a short fade and scale reveal, staggered across the four layers.
- After the reveal, each layer drifts on its own fast cycle, between 6 and 16 seconds, with a per-title offset, an 18 to 44 degree tilt and an 8 to 22 percent scale change. Layers move at different speeds so they cross, merge and separate rather than travelling as a block.
- An inner morph rotates and skews each polygon on a 9 to 17 second counter-cycle. Combined with drift, the silhouette keeps reshaping without changing its vertex data.
- Drift distances reach 14 to 36 percent of the layer size. The composition intentionally runs close to the cover edges, while the polygon vertices themselves remain inside the view box.
- Edges are softened with a 1.2 to 7.5 pixel blur. A faint same-color glow sits behind each layer, and screen blending at low opacity lets overlapping shapes merge into a translucent wash.
- Typographic fallback blurbs rise in after the artwork: the genre label first, then the title and year. The title carries a slow, low-contrast glow pulse after it settles.
- Motion uses only transform, opacity and text-shadow, so the browser can composite it on the GPU. The static blur filter is not animated.
- The global reduced-motion rule stops entrance, morph and drift cycles. The static composition and blurbs remain visible in their final position.

### 9.5 Rails and prefetch

- Title pages present similar titles in the shared horizontal rail. Roughly five to six cards are visible before the rail scrolls, with edge fades and desktop arrow controls.
- A rail that knows more content exists calls its loader when the reader is still about one viewport from the end. The next home recommendation page is six items; title-page similar titles expand from ten toward the release limit of 24.
- Loading more shows a small inline status at the end of the rail. Failures show a local Retry control and never clear already visible cards.
- Additional cards append in server order and are deduplicated. The client never constructs a recommendation cursor.

## 10. UI copy rules

### 10.1 Tone

- Concise, human, consumer-facing.
- Outcome-focused.
- Headings are short.
- Button labels are short.
- Error and empty states are calm and blame-free.

### 10.2 Prohibitions

- No architecture leaks in visible text. Banned: backend, frontend, API, endpoint, server, database, browser, client-side, sort index, payload, cache, query.
- No instructions to check consoles, servers, APIs, or logs.
- No redundant adjacent labels.
- No meta-explanations of standard UI behavior.
- No em/en dashes in UI copy, code, comments, commit messages, or markdown.
- No middle dots as UI separators.
- No internal IDs, serial numbers, provider IDs, provider names, or database values in visible UI text or labels.
- No AI pills or sparkles.
- No fake playback.

### 10.3 Metadata presentation

- Keep structural metadata separate from genres.
- Render genres as distinct chips or a separate wrapping group.
- Use `display_title` for presentation, not raw title order that exposes internal punctuation.
- Never render `title_id`, `serial_number`, or provider IDs in the UI.

## 11. Motion philosophy

- Motion is subtle, fast, and intentional.
- Hover and active transitions use short durations.
- The navbar surface transition is smooth but restrained.
- Focus and link indicators are crisp.

### 11.1 Startup intro

- Black full-screen stage for 2.8 seconds, once per browser session.
- A red light ribbon sweeps diagonally, then the CineRank mark resolves, then the wordmark fades in.
- The mark leads and the wordmark follows. The lockup never animates as one flat unit.
- Sound is on by default through a synthesized cue with a visible mute control. Autoplay policy may keep it silent until interaction.
- Reduced motion removes the ribbon and flare and shows the static lockup for 1.1 seconds.
- No skip control.

### 11.2 Loading states

- The branded page loader uses the CineRank mark, a soft red glow, a thin red progress sweep, and the loading label.
- Skeleton layouts keep their existing dimensions. Their shimmer carries a faint warm red tint instead of pure gray.
- The intro clears independently, so slow data never extends the intro. Branded loading states take over underneath.

## 12. Accessibility notes

- Use semantic HTML for nav, links, and lists.
- Keep keyboard interactions real and reachable.
- Use accessible labels where visual text is intentionally compact.
- Keep images readable with meaningful alt text or deliberate decorative treatment when appropriate.

## 13. Current component inventory

- Header: navbar, compact search, account avatar, primary nav, brand.
- AccountMenu: fixed circular avatar trigger and absolute account dropdown.
- SearchInput: debounced navbar search field and modal result dialog.
- Footer: responsive footer, brand, Explore, Community, Legal and Attribution columns, copyright strip.
- ErrorPage: shared cinematic 404 and runtime error layout.
- Logo: compact and full brand mark.
- navItems: primary nav definition.
- ProfilePage: editable identity, avatar management, active sessions, account statistics, rating history and watchlist gallery.
- IntroScreen: session-gated ribbon intro with synthesized audio and mute control.
- PageLoader: branded mark, glow, and progress sweep for pending route or session work.
- Button: shared button variants used across the app.


## Recommendation cards

The dedicated `/recommendations` page uses a responsive poster grid. Each card presents a stable rank position, canonical display title, available year/genre metadata, and a short human-readable reason only when the backend supplies one. Raw model scores are not presented as probabilities. Feedback controls are explicit, keyboard accessible, and disabled after successful submission to prevent accidental duplicate feedback. Feedback errors remain local to the affected card.


## Taste settings page

The protected `/preferences` page uses the existing page shell and form primitives. Genre controls are compact toggle chips grouped into Prefer and Exclude. The selected state is communicated with both color and `aria-pressed`. Content controls use labelled native inputs. Saving has explicit pending, error and success states. The page does not expose internal model scores or promise a percentage match.
