import { mkdtempSync, writeFileSync, existsSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { removeBlockedPublicArtifacts } from '../../../build/privateRelease.js'

describe('private production release guard', () => {
  it('keeps only clearly synthetic seed records in tracked source', () => {
    const source = readFileSync(join(process.cwd(), 'src/modules/Campaigns/talentMatchData.js'), 'utf8')
    expect(source).toContain("name: 'Synthetic Creator 01'")
    expect(source).toContain('example.invalid')
    expect(source).not.toMatch(/Rusa Chachua|Salome Gviniashvili|Zourabichvili_S/)
  })

  it('removes only the blocked public PDFs from the output directory', () => {
    const directory = mkdtempSync(join(tmpdir(), 'fs-private-release-'))
    writeFileSync(join(directory, 'ade-demo.pdf'), 'blocked')
    writeFileSync(join(directory, 'ade-demo-test.pdf'), 'blocked')
    writeFileSync(join(directory, 'reviewed.pdf'), 'keep')
    removeBlockedPublicArtifacts(directory)
    expect(existsSync(join(directory, 'ade-demo.pdf'))).toBe(false)
    expect(existsSync(join(directory, 'ade-demo-test.pdf'))).toBe(false)
    expect(existsSync(join(directory, 'reviewed.pdf'))).toBe(true)
  })
})
