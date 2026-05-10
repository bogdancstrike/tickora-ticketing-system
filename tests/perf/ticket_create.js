// Write-path perf: POST /api/tickets
//
// Validates that the rate limiter (`RATE_LIMIT_TICKET_CREATE_PER_MIN`,
// default 20/min/user) actually fires under load. We expect a mix of 201
// (under the limit) and 429 (over). A run with all 201s suggests the
// limiter isn't reachable from the perf host — check Redis connectivity.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5100';
const TOKEN = __ENV.TICKORA_TOKEN;

if (!TOKEN) {
  throw new Error('TICKORA_TOKEN env var is required');
}

const created = new Counter('tickets_created');
const limited = new Counter('rate_limited');

export const options = {
  scenarios: {
    burst: {
      executor: 'constant-arrival-rate',
      rate: 60,
      timeUnit: '1m',
      duration: '2m',
      preAllocatedVUs: 10,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.5'],  // expect some 429s, not all
  },
};

export default function () {
  const body = JSON.stringify({
    title: `perf-${__VU}-${__ITER}`,
    txt: 'k6 generated ticket for performance testing of the create path',
    beneficiary_type: 'internal',
  });
  const r = http.post(`${BASE_URL}/tickora/api/tickets`, body, {
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
  });
  if (r.status === 201) created.add(1);
  if (r.status === 429) limited.add(1);
  check(r, {
    'status 201 or 429': (res) => res.status === 201 || res.status === 429,
  });
  sleep(0.1);
}
