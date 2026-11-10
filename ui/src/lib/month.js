// Largest number of complete rows that fits, reserving overflow control space only if needed.
export function fittingRows(total, height, rowHeight, moreHeight, gap = 0) {
  if (total * (rowHeight + gap) - gap <= height) return total
  return Math.min(total, Math.max(0, Math.floor((height - moreHeight) / (rowHeight + gap))))
}
