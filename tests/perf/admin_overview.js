// Admin overview perf: GET /api/admin/overview
//
// Includes active_sessions (Redis SCAN), KPIs (counts), recent audit
// queries, and a global monitor delegated call. Goal: p95 < 1.5 s.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5100';
const TOKEN = __ENV.TICKORA_TOKEN;

if (!TOKEN) {
  throw new Error('TICKORA_TOKEN env var is required');
}

export const options = {
  scenarios: {
    admins: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 10 },
        { duration: '1m',  target: 10 },
        { duration: '20s', target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<1500'],
    http_req_failed:   ['rate<0.01'],
  },
};

export default function () {
  const r = http.get(`${BASE_URL}/tickora/api/admin/overview`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  });
  check(r, { 'status 200': (res) => res.status === 200 });
  sleep(1);
}
