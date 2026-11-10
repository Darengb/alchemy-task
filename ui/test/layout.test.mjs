import test from 'node:test'
import assert from 'node:assert/strict'
import { fittingRows } from '../src/lib/month.js'
import { parseBlocks, renderBlocks } from '../src/lib/markdown.js'

test('month fits complete rows and reserves overflow only when necessary', () => {
  assert.equal(fittingRows(0, 100, 24, 18, 1), 0)
  assert.equal(fittingRows(4, 99, 24, 18, 1), 4)
  assert.equal(fittingRows(5, 99, 24, 18, 1), 3)
  assert.equal(fittingRows(10, 143, 24, 18, 1), 5)
  assert.equal(fittingRows(10, 117, 24, 18, 1), 3)
  assert.equal(fittingRows(3, 20, 24, 18, 1), 0)
})

test('overflow capacity is maximal and never overlaps the overflow control', () => {
  for (let height = 18; height <= 300; height++) {
    for (let total = 1; total <= 20; total++) {
      const n = fittingRows(total, height, 24, 18, 1)
      if (n === total) assert.ok(n * 25 - 1 <= height)
      else {
        assert.ok(n * 25 + 18 <= height)
        assert.ok((n + 1) * 25 + 18 > height)
      }
    }
  }
})

test('time wrapping follows header semantics rather than column position', () => {
  for (const headers of [['Section', 'Time', 'What'], ['Duration', 'Description', 'Section'], ['Section', 'What', 'Time']]) {
    const block = parseBlocks(`| ${headers.join(' | ')} |\n|---|---|---|\n| sample | sample | sample |`)
    const table = renderBlocks(block)[0].props.children
    const head = table.props.children[0].props.children.props.children
    const row = table.props.children[1].props.children[0].props.children
    headers.forEach((h, i) => {
      const expected = /^(Time|Duration)$/.test(h) ? 'at-md-time' : undefined
      assert.equal(head[i].props.className, expected)
      assert.equal(row[i].props.className, expected)
    })
  }
})
