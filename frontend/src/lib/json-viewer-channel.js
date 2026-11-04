const CHANNEL_PREFIX = 'hi-scenario-json:';
export const JSON_REQUEST_TIMEOUT_MS = 5000;

/** Respond only to explicit requests, reading the form at the time of the request.
 * @param {() => string} getJson
 */
export function createJsonSource(getJson) {
  const id = crypto.randomUUID();
  const channel = new BroadcastChannel(CHANNEL_PREFIX + id);
  /** @param {MessageEvent} event */
  const respond = ({ data }) => {
    if (data?.type === 'request-json' && typeof data.requestId === 'string') {
      channel.postMessage({ type: 'scenario-json', requestId: data.requestId, json: getJson() });
    }
  };
  channel.addEventListener('message', respond);
  return { id, close: () => { channel.removeEventListener('message', respond); channel.close(); } };
}

/** One request per refresh; no open viewer channel or timer remains after it settles.
 * @param {string} sourceId
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<string>}
 */
export function requestScenarioJson(sourceId, { signal } = {}) {
  return new Promise((resolve, reject) => {
    if (!/^[a-f0-9-]{36}$/i.test(sourceId)) {
      reject(new Error('Missing Builder connection.'));
      return;
    }
    if (signal?.aborted) {
      reject(new DOMException('Request cancelled.', 'AbortError'));
      return;
    }
    const channel = new BroadcastChannel(CHANNEL_PREFIX + sourceId);
    const requestId = crypto.randomUUID();
    let settled = false;
    /** @param {Error | null} error @param {string} [json] */
    function finish(error, json = '') {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      channel.removeEventListener('message', receive);
      channel.removeEventListener('messageerror', failed);
      channel.close();
      if (error) reject(error);
      else resolve(json);
    }
    const abort = () => finish(new DOMException('Request cancelled.', 'AbortError'));
    const failed = () => finish(new Error('Could not retrieve the snapshot.'));
    /** @param {MessageEvent} event */
    const receive = ({ data }) => {
      if (data?.type !== 'scenario-json' || data.requestId !== requestId) return;
      try {
        if (typeof data.json !== 'string') throw new Error('Missing JSON.');
        finish(null, JSON.stringify(JSON.parse(data.json), null, 2));
      } catch { failed(); }
    };
    const timer = setTimeout(failed, JSON_REQUEST_TIMEOUT_MS);
    channel.addEventListener('message', receive);
    channel.addEventListener('messageerror', failed);
    signal?.addEventListener('abort', abort, { once: true });
    try { channel.postMessage({ type: 'request-json', requestId }); }
    catch { failed(); }
  });
}
