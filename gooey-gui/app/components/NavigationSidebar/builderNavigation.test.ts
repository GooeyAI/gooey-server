import {
  builderOpenEventName,
  navigationStateWithoutBuilderIntent,
} from "./builderNavigation";

function main() {
  assertEqual(
    builderOpenEventName("builder-sidebar", "open"),
    "builder-sidebar:open"
  );
  assertEqual(builderOpenEventName("builder-sidebar", null), null);
  assertDeepEqual(
    navigationStateWithoutBuilderIntent({
      builderIntent: "open",
      recipeView: "split",
    }),
    { recipeView: "split" }
  );
}

function assertEqual(actual: unknown, expected: unknown) {
  if (actual !== expected) {
    throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  }
}

function assertDeepEqual(actual: unknown, expected: unknown) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`Expected ${expectedJson}, received ${actualJson}`);
  }
}

main();
