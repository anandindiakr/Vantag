export async function localApi<T>(path: string, body?: unknown, method = body === undefined ? 'GET' : 'POST', signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  if (signal?.aborted) controller.abort();
  else signal?.addEventListener('abort', cancel, { once: true });
  const timeoutMs = path.startsWith('onvif/') ? 120000 : method === 'GET' ? 15000 : 60000;
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetch(`/api/${path}`, { method, credentials: 'same-origin', signal: controller.signal, headers: body === undefined ? {} : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    if (response.status === 401 && path !== 'login' && path !== 'setup') {
      window.dispatchEvent(new Event('local-session-expired'));
      throw new Error('Your local session has expired. Sign in locally again.');
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      const details = Array.isArray(error.detail) ? error.detail.slice(0, 3).map((item: { loc?: unknown[]; msg?: string }) => `${Array.isArray(item.loc) ? item.loc.filter(part => part !== 'body').join(' / ') : 'Field'}: ${typeof item.msg === 'string' ? item.msg : 'Invalid value'}`).join('; ') : '';
      throw new Error(typeof error.detail === 'string' ? error.detail : details || `Request failed (${response.status})`);
    }
    return await response.json();
  } catch (cause) {
    if (signal?.aborted) throw cause;
    if (timedOut) throw new Error('The local agent request timed out. Your form is still here. Check that VantagAgent is running and inspect Licence & health. Before repeating a save, check Saved cameras: the operation may already have completed.');
    if (cause instanceof Error && cause.name === 'TypeError') throw new Error('Cannot reach the local agent service. Keep VantagAgent running and reopen its local dashboard; internet access is not required.');
    throw cause;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}
