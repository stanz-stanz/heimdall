import { writable, get } from 'svelte/store';
import en from '../messages/en.json';
import da from '../messages/da.json';

const dicts = { en, da };

export const locale = writable('en');

export function setLocale(next) {
  if (!Object.prototype.hasOwnProperty.call(dicts, next)) return;
  locale.set(next);
}

export function t(key) {
  const active = get(locale);
  const dict = dicts[active] || {};
  if (Object.prototype.hasOwnProperty.call(dict, key)) {
    return dict[key];
  }
  if (Object.prototype.hasOwnProperty.call(dicts.en, key)) {
    return dicts.en[key];
  }
  return key;
}
