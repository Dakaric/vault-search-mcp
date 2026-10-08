from collections.abc import Iterable
from types import ModuleType

from installer import ui
from installer.model import Context, Result


def _run_component(component: ModuleType, ctx: Context) -> Result:
    support = component.supported(ctx.platform)
    print(f"\n{component.TITLE} ({component.KEY}): {support.state}. {support.reason}")
    print(component.DESCRIPTION)
    if support.state == "nein":
        return Result(component.KEY, "nicht unterstützt", support.reason)
    # Dry-Runs bleiben auch bei ausgeschalteten Diensten vollständig offline.
    if not ctx.dry_run and component.is_done(ctx):
        return Result(component.KEY, "übersprungen", "schon eingerichtet")
    if not ui.ask_yes_no("Diesen Baustein ausführen?", component.DEFAULT, ctx):
        return Result(component.KEY, "übersprungen", "nicht gewählt")
    steps = component.plan(ctx)
    for step in steps:
        print(f"  {step}")
    if ctx.dry_run:
        return Result(component.KEY, "übersprungen", "Dry-Run: " + "; ".join(steps))
    return component.apply(ctx)


def run_components(
    components: Iterable[ModuleType], ctx: Context, only: set[str] | None = None
) -> list[Result]:
    results = []
    for component in components:
        if only is not None and component.KEY not in only:
            continue
        try:
            results.append(_run_component(component, ctx))
        except Exception as error:
            results.append(Result(component.KEY, "fehler", str(error)))
    return results
