// The /signup/start page reads ?t=<token> at runtime; prerendering it
// would bake an empty-token state into the static bundle. Disable
// prerender — adapter-static still serves the route from the SPA
// fallback at build/404.html.
export const prerender = false;
export const ssr = false;
