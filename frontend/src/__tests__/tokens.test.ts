import { darken, flavor, mix, typography } from '../theme/tokens';

describe('color math', () => {
  it('mixes linearly', () => {
    expect(mix('#000000', '#FFFFFF', 0.5)).toBe('#808080');
  });
  it('darkens toward black', () => {
    expect(darken('#FFFFFF', 0.25)).toBe('#BFBFBF');
  });
});

describe('flavor tokens are derived by formula', () => {
  it('umami: base -> tint (88% paper) / ink (darkened 25%)', () => {
    expect(flavor.umami.base).toBe('#B0742F');
    expect(flavor.umami.tint).toBe('#F2E7D9');
    expect(flavor.umami.ink).toBe('#845723');
  });
  it('every dim has all four derived colors', () => {
    Object.values(flavor).forEach((t) => {
      expect(t).toEqual(
        expect.objectContaining({
          base: expect.any(String),
          tint: expect.any(String),
          ink: expect.any(String),
          inkDark: expect.any(String),
        }),
      );
    });
  });
});

describe('type scale', () => {
  it('uses Fraunces for display, Hanken for body', () => {
    expect(typography.display.fontFamily).toBe('Fraunces_600SemiBold');
    expect(typography.body.fontFamily).toBe('HankenGrotesk_400Regular');
  });
});
