import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// The whole suite runs in parallel in one container: give findBy* queries time under load (the default is 1 s).
configure({ asyncUtilTimeout: 3000 });
