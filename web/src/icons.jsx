/**
 * Line icons, straight out of the design: 24x24 viewBox, 1.75 stroke, round
 * caps and joins throughout, `currentColor` so they inherit whatever ink or
 * chrome colour they're set in. Typographic marks are deliberately not used
 * here -- the design's chrome stays monochrome and drawn, not emoji.
 */
function Icon({ size = 20, children, viewBox = '0 0 24 24' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

export function IconToday(props) {
  return (
    <Icon {...props}>
      <path d="M12 4.6v2.2" />
      <path d="M5.9 7.4 7.5 9" />
      <path d="M18.1 7.4 16.5 9" />
      <path d="M7.4 15.6a4.6 4.6 0 0 1 9.2 0" />
      <path d="M3.6 15.6h16.8" />
      <path d="M6.6 19.4h10.8" />
    </Icon>
  )
}

export function IconRead(props) {
  return (
    <Icon {...props}>
      <path d="M12 7.2v12.4" />
      <path d="M12 7.2C10.4 6 8 5.5 5 5.7v12.1c3-.2 5.4.3 7 1.5 1.6-1.2 4-1.7 7-1.5V5.7c-3-.2-5.4.3-7 1.5Z" />
    </Icon>
  )
}

export function IconSearch(props) {
  return (
    <Icon {...props}>
      <circle cx="10.7" cy="10.7" r="5.7" />
      <path d="M14.9 14.9 19.4 19.4" />
    </Icon>
  )
}

export function IconNote(props) {
  return (
    <Icon {...props}>
      <path d="M5.2 18.8h3l9.9-9.9a2.1 2.1 0 0 0-3-3L5.2 15.8v3Z" />
      <path d="M14.6 6.4l3 3" />
    </Icon>
  )
}

export function IconBookmark(props) {
  return (
    <Icon {...props}>
      <path d="M7 4.9h10v14.2l-5-3.5-5 3.5V4.9Z" />
    </Icon>
  )
}

export function IconPlay({ size = 17, ...rest }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" {...rest}>
      <path d="M8.6 5.6 18.4 12l-9.8 6.4V5.6Z" fill="currentColor" />
    </svg>
  )
}

export function IconShare(props) {
  return (
    <Icon {...props}>
      <path d="M12 15.2V4.9" />
      <path d="M8.5 8.4 12 4.9l3.5 3.5" />
      <path d="M6.2 13.4v5.7h11.6v-5.7" />
    </Icon>
  )
}

export function IconChevronDown(props) {
  return (
    <Icon {...props}>
      <path d="M6.8 9.8 12 14.9l5.2-5.1" />
    </Icon>
  )
}

export function IconChevronLeft(props) {
  return (
    <Icon {...props}>
      <path d="M14 6.6 8.6 12 14 17.4" />
    </Icon>
  )
}

export function IconChevronRight(props) {
  return (
    <Icon {...props}>
      <path d="M10 6.6 15.4 12 10 17.4" />
    </Icon>
  )
}

export function IconClose(props) {
  return (
    <Icon {...props}>
      <path d="M6.6 6.6 17.4 17.4" />
      <path d="M17.4 6.6 6.6 17.4" />
    </Icon>
  )
}

export function IconSidebar(props) {
  return (
    <Icon {...props}>
      <rect x="4" y="5.6" width="16" height="12.8" rx="2.6" />
      <path d="M9.8 5.6v12.8" />
    </Icon>
  )
}

export function IconTopic(props) {
  return (
    <Icon {...props}>
      <path d="M12.7 4.9h6.4v6.4l-7.8 7.8-6.4-6.4 7.8-7.8Z" />
      <circle cx="15.9" cy="8.1" r="1.3" />
    </Icon>
  )
}

/** The "Original" glyph: a lowercase alpha set in the reading serif. */
export function IconOriginal({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <text
        x="12"
        y="17.6"
        textAnchor="middle"
        fontFamily="var(--font-serif)"
        fontSize="19"
        fill="currentColor"
      >
        α
      </text>
    </svg>
  )
}

export function IconThread({ size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="currentColor" />
    </svg>
  )
}

/** The mark above the verse of the day. Four points, drawn, not an emoji. */
export function IconOrnament({ size = 18 }) {
  return (
    <Icon size={size}>
      <path d="M12 3.4c0 4.2 2.4 6.6 6.6 6.6-4.2 0-6.6 2.4-6.6 6.6 0-4.2-2.4-6.6-6.6-6.6 4.2 0 6.6-2.4 6.6-6.6Z" />
    </Icon>
  )
}

/** Day reading. */
export function IconSun({ size = 15 }) {
  return (
    <Icon size={size}>
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 2.6v2.2M12 19.2v2.2M4.2 12H2M22 12h-2.2M6.5 6.5 4.9 4.9M19.1 19.1l-1.6-1.6M17.5 6.5l1.6-1.6M4.9 19.1l1.6-1.6" />
    </Icon>
  )
}

/** Night reading. */
export function IconMoon({ size = 15 }) {
  return (
    <Icon size={size}>
      <path d="M20 14.2A8.4 8.4 0 0 1 9.8 4a8.4 8.4 0 1 0 10.2 10.2Z" />
    </Icon>
  )
}
