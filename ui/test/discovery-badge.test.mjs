import test from 'node:test'
import assert from 'node:assert/strict'
import { discoveryBadge, pendingCount } from '../src/lib/discovery.js'

const run = (states) => ({ proposals: states.map((state) => ({ state })) })

test('badge shows 1 while discovery has never been set up', () => {
  assert.equal(discoveryBadge([], []), 1)
})

test('no setup badge once a stream exists, even before its first run', () => {
  assert.equal(discoveryBadge([], [{ name: 'mbg' }]), 0)
})

test('no setup badge while runs or streams are unknown (loading or error)', () => {
  assert.equal(discoveryBadge(null, []), 0)
  assert.equal(discoveryBadge([], null), 0)
})

test('pending proposals still drive the badge', () => {
  assert.equal(discoveryBadge([run(['pending', 'pending', 'created'])], [{ name: 'mbg' }]), 2)
  assert.equal(pendingCount([run(['pending'])]), 1)
  assert.equal(discoveryBadge([run(['created'])], [{ name: 'mbg' }]), 0)
})
