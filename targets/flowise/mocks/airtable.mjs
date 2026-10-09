import http from 'node:http'

const port = Number(process.env.PORT || 4567)
const records = [
  { id: 'rec-agentfuzz-1', createdTime: '2026-01-01T00:00:00.000Z', fields: { name: 'example', value: 42 } },
  { id: 'rec-agentfuzz-2', createdTime: '2026-01-02T00:00:00.000Z', fields: { name: 'second', value: 7 } }
]

const server = http.createServer((request, response) => {
  console.log(`${request.method} ${request.url}`)
  if (request.url === '/health') {
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify({ status: 'ok' }))
    return
  }
  if (request.method === 'GET' && /^\/v0\/[^/]+\/[^/?]+/.test(request.url || '')) {
    response.writeHead(200, { 'content-type': 'application/json' })
    response.end(JSON.stringify({ records }))
    return
  }
  response.writeHead(404, { 'content-type': 'application/json' })
  response.end(JSON.stringify({ error: 'not found' }))
})

server.listen(port, '0.0.0.0', () => {
  console.log(`Airtable mock listening on ${port}`)
})
