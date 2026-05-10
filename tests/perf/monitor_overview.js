// Monitor overview perf: GET /api/monitor/overview?days=30
//
// First hit per (visibility class, days) bucket runs the full aggregate.
// The 60-s Redis cache should bring subsequent hits under ~100 ms. The
// stage shape reflects that — we ramp up fast to make the cache earn its
// keep.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5100';
const TOKEN = __ENV.TICKORA_TOKEN;

if (!TOKEN) {
  throw new Error('TICKORA_TOKEN env var is required');
}

export const options = {
  scenarios: {
    cached_path: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '15s', target: 30 },
        { duration: '1m',  target: 30 },
        { duration: '15s', target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: [
      'p(95)<1500',  // includes the cold first hit
      'p(50)<200',   // warm cache should dominate
    ],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const r = http.get(`${BASE_URL}/tickora/api/monitor/overview?days=30`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  });
  check(r, { 'status 200': (res) => res.status === 200 });
  sleep(0.5);
}
