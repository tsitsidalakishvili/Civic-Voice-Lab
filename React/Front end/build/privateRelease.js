import { existsSync, rmSync } from 'node:fs'
import { resolve } from 'node:path'

export const BLOCKED_PUBLIC_ARTIFACTS = ['ade-demo.pdf', 'ade-demo-test.pdf']

export function removeBlockedPublicArtifacts(outDir) {
  for (const fileName of BLOCKED_PUBLIC_ARTIFACTS) {
    const target = resolve(outDir, fileName)
    if (existsSync(target)) rmSync(target, { force: true })
  }
}

export function privateReleaseGuard({ production, outDir }) {
  return {
    name: 'fs-private-release-guard',
    closeBundle() {
      if (production) removeBlockedPublicArtifacts(outDir)
    },
  }
}
