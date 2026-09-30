import { ApiError } from '../api/client'

export type ChatEvent =
  | { event: 'delta'; data: { text: string } }
  | { event: 'status'; data: { text: string } }
  | { event: 'done'; data: { unverified: string[]; spent_usd: number | null; budget_usd: number | null } }
  | { event: 'error'; data: { message: string } }

/**
 * POST a question and read the answer as server-sent events (backend/chat.py). EventSource can't
 * POST, so the stream is parsed from the fetch body. Throws ApiError if the request is refused.
 */
export async function streamChat(url: string, message: string, onEvent: (e: ChatEvent) => void, signal?: AbortSignal) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal,
  })
  if (!res.ok || !res.body) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, String(detail))
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let end: number
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      let event = 'message'
      let data = ''
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (data) onEvent({ event, data: JSON.parse(data) } as ChatEvent)
    }
  }
}
