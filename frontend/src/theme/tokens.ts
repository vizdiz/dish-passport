/**
 * Dish Passport design tokens — authored from the design system spec.
 *
 * The defining rule: the 10 flavor dimensions are first-class color tokens. One fixed `base`
 * per dimension; `tint`/`ink` are DERIVED BY FORMULA (never hand-picked) so chips, the spectrum
 * bar, and the lollipop list all match exactly:
 *   tint = base mixed 88% with paper   (chip background)
 *   ink  = base darkened ~25%          (text/label on tint)
 *   dark mode keeps `base` for the mark and lightens `ink` one step for legibility.
 *
 * Fonts: Fraunces for dish names / screen titles / empty-state headlines ONLY; Hanken Grotesk
 * for everything else (body, labels, buttons, all numbers with tabular figures).
 */

// ----------------------------------------------------------------------------- color math

interface RGB {
  r: number;
  g: number;
  b: number;
}

function hexToRgb(hex: string): RGB {
  const h = hex.replace('#', '');
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

function channel(n: number): string {
  return Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
}

function rgbToHex({ r, g, b }: RGB): string {
  return `#${channel(r)}${channel(g)}${channel(b)}`.toUpperCase();
}

/** Linear sRGB mix; `amount` is the weight of `b` (0 => all a, 1 => all b). */
export function mix(a: string, b: string, amount: number): string {
  const ca = hexToRgb(a);
  const cb = hexToRgb(b);
  return rgbToHex({
    r: ca.r + (cb.r - ca.r) * amount,
    g: ca.g + (cb.g - ca.g) * amount,
    b: ca.b + (cb.b - ca.b) * amount,
  });
}

/** Move `amount` of the way toward black. */
export function darken(hex: string, amount: number): string {
  return mix(hex, '#000000', amount);
}

/** Move `amount` of the way toward white. */
export function lighten(hex: string, amount: number): string {
  return mix(hex, '#FFFFFF', amount);
}

// ----------------------------------------------------------------------------- base palette

export const color = {
  paper: '#FBF7F0', // app background
  surface: '#FFFDFB', // cards
  ink: '#2A2320', // text primary
  muted: '#6E635B', // text secondary
  hint: '#A89E94', // text tertiary
  hairline: '#ECE3D8', // borders
  accent: '#DB5A2E', // paprika
  accentPress: '#B8431F',
  deep: '#1F6F5C', // pine, sparing
  success: '#2E7D5B',
  warning: '#C9871F',
  danger: '#C23B2E', // == "not for me"
} as const;

// ----------------------------------------------------------------------------- flavor tokens

/** The 10 flavor dimensions, in canonical order (matches the backend `flavor` vector). */
export const FLAVOR_DIMS = [
  'umami',
  'spicy',
  'sour',
  'sweet',
  'bitter',
  'rich',
  'herbaceous',
  'smoky',
  'fermented',
  'fresh',
] as const;

export type FlavorDim = (typeof FLAVOR_DIMS)[number];

const FLAVOR_BASE: Record<FlavorDim, string> = {
  umami: '#B0742F',
  spicy: '#D6452C',
  sour: '#B5C13A',
  sweet: '#E08AA6',
  bitter: '#4E5A28',
  rich: '#8E4A45',
  herbaceous: '#5C9A4A',
  smoky: '#5A6470',
  fermented: '#7E5AA0',
  fresh: '#2BA6B0',
};

const TINT_PAPER_WEIGHT = 0.88; // tint = base mixed 88% with paper
const INK_DARKEN = 0.25; // ink  = base darkened ~25%
const INK_DARK_LIFT = 0.18; // dark mode: lighten ink one step

export interface FlavorToken {
  base: string; // the mark (chips/dots/segments) in both light and dark
  tint: string; // chip background (light)
  ink: string; // text/label on tint (light)
  inkDark: string; // text/label on tint (dark mode)
}

function deriveFlavor(base: string): FlavorToken {
  const ink = darken(base, INK_DARKEN);
  return {
    base,
    tint: mix(base, color.paper, TINT_PAPER_WEIGHT),
    ink,
    inkDark: lighten(ink, INK_DARK_LIFT),
  };
}

export const flavor: Record<FlavorDim, FlavorToken> = Object.fromEntries(
  FLAVOR_DIMS.map((dim) => [dim, deriveFlavor(FLAVOR_BASE[dim])]),
) as Record<FlavorDim, FlavorToken>;

export function flavorToken(dim: FlavorDim): FlavorToken {
  return flavor[dim];
}

// ----------------------------------------------------------------------------- fonts

export const fonts = {
  fraunces: {
    400: 'Fraunces_400Regular',
    500: 'Fraunces_500Medium',
    600: 'Fraunces_600SemiBold',
  },
  hanken: {
    400: 'HankenGrotesk_400Regular',
    500: 'HankenGrotesk_500Medium',
    600: 'HankenGrotesk_600SemiBold',
    700: 'HankenGrotesk_700Bold',
  },
} as const;

type FontFamily = 'fraunces' | 'hanken';

export interface TypeStyle {
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  fontWeight: '400' | '500' | '600' | '700';
  letterSpacing?: number;
}

function type(
  family: FontFamily,
  weight: 400 | 500 | 600 | 700,
  size: number,
  lineHeight: number,
): TypeStyle {
  const fontFamily = (fonts[family] as Record<number, string>)[weight];
  // Fraunces ships with -2% tracking per the spec; Hanken sits at default.
  const letterSpacing = family === 'fraunces' ? -0.02 * size : undefined;
  return { fontFamily, fontSize: size, lineHeight, fontWeight: String(weight) as TypeStyle['fontWeight'], letterSpacing };
}

/** Type scale: size / line-height / weight / family, exactly per spec. */
export const typography = {
  display: type('fraunces', 600, 28, 34),
  h1: type('fraunces', 600, 24, 30),
  h2: type('hanken', 600, 18, 24),
  title: type('hanken', 600, 16, 22),
  body: type('hanken', 400, 15, 22),
  label: type('hanken', 500, 13, 18),
  caption: type('hanken', 500, 12, 16),
  micro: type('hanken', 500, 11, 14),
} as const;

export type TypeVariant = keyof typeof typography;

/** Apply to any numeric text so figures align (Hanken tabular figures). */
export const tabularNumbers = { fontVariant: ['tabular-nums'] as ['tabular-nums'] };

// ----------------------------------------------------------------------------- layout

/** 4pt spacing grid. */
export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  '2xl': 32,
  '3xl': 48,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 999,
} as const;

export const border = {
  hairline: 1, // StyleSheet.hairlineWidth is applied at use sites; this is the token value
  color: color.hairline,
} as const;

/** Two near-invisible elevation tokens — the palette wants flatness. */
export const elevation = {
  e1: {
    // cards
    shadowColor: '#2A2320',
    shadowOpacity: 0.04,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  e2: {
    // sheets
    shadowColor: '#2A2320',
    shadowOpacity: 0.08,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },
} as const;

// ----------------------------------------------------------------------------- dark mode

/** Dark palette: backgrounds invert toward ink, flavor marks keep their `base`. */
export const colorDark = {
  paper: '#1A1613',
  surface: '#241F1B',
  ink: '#F3ECE3',
  muted: '#B7ABA0',
  hint: '#7C7269',
  hairline: '#3A332D',
  accent: '#E2683D',
  accentPress: '#C8511F',
  deep: '#3E9C84',
  success: '#46A578',
  warning: '#D89B3A',
  danger: '#D85546',
} as const;

export type ColorScheme = 'light' | 'dark';

/** Resolve a flavor token's foreground color for the active scheme. */
export function flavorInk(dim: FlavorDim, scheme: ColorScheme): string {
  return scheme === 'dark' ? flavor[dim].inkDark : flavor[dim].ink;
}

export const tokens = {
  color,
  colorDark,
  flavor,
  fonts,
  typography,
  tabularNumbers,
  space,
  radius,
  border,
  elevation,
  FLAVOR_DIMS,
} as const;

export default tokens;
