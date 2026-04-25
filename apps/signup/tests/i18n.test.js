import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { t, locale, setLocale } from '$lib/i18n';

describe('i18n', () => {
  beforeEach(() => {
    setLocale('en');
  });

  it('returns the EN string for a known key', () => {
    expect(t('nav.brand')).toBe('Digital Vagt');
  });

  it('falls back to EN when the DA dict is missing the key', () => {
    setLocale('da');
    expect(t('nav.brand')).toBe('Digital Vagt');
  });

  it('returns the key itself when neither locale has it', () => {
    expect(t('nonexistent.key')).toBe('nonexistent.key');
  });

  it('updates locale via setLocale', () => {
    setLocale('da');
    expect(get(locale)).toBe('da');
    setLocale('en');
    expect(get(locale)).toBe('en');
  });

  it('ignores unknown locale codes', () => {
    setLocale('en');
    setLocale('zz');
    expect(get(locale)).toBe('en');
  });
});
