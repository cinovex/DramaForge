import { createExtConfig } from "@toonflow/ext-scaffold";
import metadata from "./src/metadata.ts";

export default createExtConfig(metadata, import.meta.url);
