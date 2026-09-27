// ponytail: project-owned shim until rtk-ai/rtk#3463 ships an OpenCode V2 plugin; delete this file then.
import { execFileSync } from "node:child_process"

// Module-private: not part of the plugin contract. Accept a rewrite only on exit 0 or
// rtk's declined-but-suggested exit 3, both with non-empty stdout; anything else
// (timeout, signal, missing binary, exit 1/2, empty stdout) leaves the command unchanged.
function rewriteCommand(command: string): string {
  let out = ""
  let status: number | null = 0
  try {
    out = execFileSync("rtk", ["rewrite", command], { encoding: "utf8", timeout: 2000, windowsHide: true })
  } catch (err: any) {
    status = typeof err?.status === "number" ? err.status : null
    out = typeof err?.stdout === "string" ? err.stdout : ""
  }
  const trimmed = out.trim()
  const accepted = (status === 0 || status === 3) && trimmed.length > 0
  return accepted ? trimmed : command
}

export default {
  id: "rtk",
  async setup(ctx: any) {
    // OpenCode v2.0.18 packages/core/src/shell.ts:274 fires create.before first; only then
    // does the shell tool's prepare (packages/core/src/tool/plugin/shell.ts ~116-136, called
    // ~210) scan the command and run permission.assert. So the check sees the REWRITTEN
    // command (`rtk git push ...`). The kit renders an `rtk ` twin of every shell rule
    // (Add-SwRtkTwins in .sw/lib/Sw.Project.psm1) so rewritten commands get the same decision.
    try {
      await ctx?.shell?.hook?.("create.before", (e: { command: string }) => {
        e.command = rewriteCommand(e.command)
      })
    } catch {
      // never throw out of setup
    }
  },
}
