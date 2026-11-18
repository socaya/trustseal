/* Load the bundled Y.js ESM and attach the needed exports on window.Y
 * so the classic editor script can treat it as a global library.
 *
 * Fires a "yjs-ready" CustomEvent when the import resolves. */
import * as Y from './yjs.bundle.mjs';
window.Y = Y;
window.dispatchEvent(new CustomEvent('yjs-ready'));
