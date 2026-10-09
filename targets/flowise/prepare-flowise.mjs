const base = process.env.AGENTFUZZ_FLOWISE_URL || 'http://127.0.0.1:3000'
const email = process.env.AGENTFUZZ_FLOWISE_TEST_EMAIL || 'agentfuzz@example.invalid'
const password = process.env.AGENTFUZZ_FLOWISE_TEST_PASSWORD || 'AgentFuzz-test-password-2026!'
const model = process.env.AGENTFUZZ_TARGET_MODEL_NAME
const baseUrl = process.env.AGENTFUZZ_TARGET_MODEL_BASE_URL
const apiKey = process.env.AGENTFUZZ_TARGET_MODEL_API_KEY

async function request(path, options = {}) {
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { 'content-type': 'application/json', ...(options.headers || {}) }
  })
  const text = await response.text()
  let body
  try { body = JSON.parse(text) } catch { body = text }
  if (!response.ok) throw new Error(`${path} returned ${response.status}: ${text}`)
  return { body, headers: response.headers }
}

let registration
try {
  registration = await request('/api/v1/account/register', {
    method: 'POST',
    body: JSON.stringify({ user: { name: 'AgentFuzz', email, credential: password } })
  })
} catch (error) {
  // A rerun in the same workspace is allowed: the account already exists.
  if (!String(error).includes('already exists')) throw error
}

const login = await request('/api/v1/auth/login', {
  method: 'POST',
  body: JSON.stringify({ email, password })
})
const cookieHeaders = login.headers.getSetCookie?.() || [login.headers.get('set-cookie') || '']
const cookies = cookieHeaders.map((item) => item.split(';', 1)[0].trim()).filter(Boolean)
const cookie = cookies.join('; ')
if (!cookies.some((item) => item.startsWith('token='))) throw new Error('Flowise login did not return a token cookie')

const chatflow = {
  name: 'AgentFuzz Airtable reproduction',
  type: 'CHATFLOW',
  deployed: true,
  isPublic: true,
  flowData: JSON.stringify({
    nodes: [
      {
        id: 'chatOpenAI_0', type: 'customNode', position: { x: 0, y: 0 },
        data: {
          id: 'chatOpenAI_0', label: 'ChatOpenAI', name: 'chatOpenAI', type: 'ChatOpenAI',
          category: 'Chat Models', inputParams: [], inputAnchors: [], outputAnchors: [
            { id: 'chatOpenAI_0-output-chatOpenAI-ChatOpenAI|BaseChatModel|BaseLanguageModel|Runnable', name: 'chatOpenAI', label: 'ChatOpenAI', type: 'ChatOpenAI | BaseChatModel | BaseLanguageModel | Runnable' }
          ], outputs: {}, inputs: {
            modelName: model, temperature: '0', basepath: baseUrl, openAIApiKey: apiKey, streaming: false
          }
        }
      },
      {
        id: 'airtableAgent_0', type: 'customNode', position: { x: 400, y: 0 },
        data: {
          id: 'airtableAgent_0', label: 'Airtable Agent', name: 'airtableAgent', type: 'AgentExecutor',
          category: 'Agents', inputParams: [], inputAnchors: [], outputAnchors: [], outputs: {},
          inputs: {
            model: '{{chatOpenAI_0.data.instance}}', baseId: 'app-agentfuzz', tableId: 'tbl-agentfuzz',
            returnAll: true, accessToken: 'agentfuzz-mock-token'
          }
        }
      }
    ],
    edges: [{
      id: 'chatOpenAI_0-airtableAgent_0', source: 'chatOpenAI_0', target: 'airtableAgent_0',
      sourceHandle: 'chatOpenAI_0-output-chatOpenAI-ChatOpenAI|BaseChatModel|BaseLanguageModel|Runnable',
      targetHandle: 'airtableAgent_0-input-model-BaseLanguageModel'
    }]
  })
}
const created = await request('/api/v1/chatflows', {
  method: 'POST', headers: { Cookie: cookie, 'x-request-from': 'internal' }, body: JSON.stringify(chatflow)
})
const id = created.body?.id
if (!id) throw new Error(`Flowise did not return a chatflow id: ${JSON.stringify(created.body)}`)
await import('node:fs/promises').then((fs) => fs.writeFile('/workspace/target.env', `AGENTFUZZ_FLOWISE_CHATFLOW_ID=${id}\n`))
console.log(`Prepared Flowise chatflow ${id}`)
