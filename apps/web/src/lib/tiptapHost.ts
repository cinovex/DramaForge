import * as core from "@tiptap/core";
import * as vue3 from "@tiptap/vue-3";
import * as starterKit from "@tiptap/starter-kit";
import * as markdown from "@tiptap/markdown";
import * as findAndReplace from "@tiptap/extension-find-and-replace";
import * as highlight from "@tiptap/extension-highlight";
import * as image from "@tiptap/extension-image";
import * as list from "@tiptap/extension-list";
import * as subscript from "@tiptap/extension-subscript";
import * as superscript from "@tiptap/extension-superscript";
import * as table from "@tiptap/extension-table";
import * as textAlign from "@tiptap/extension-text-align";
import * as model from "@tiptap/pm/model";
import * as state from "@tiptap/pm/state";
import * as view from "@tiptap/pm/view";
import * as marked from "marked";
import dompurify from "dompurify";

Object.assign(globalThis, { toonflowTiptapHost: {
  core, vue3, starterKit, markdown, findAndReplace, highlight, image, list, subscript, superscript, table, textAlign, model, state, view, marked, dompurify,
} });
