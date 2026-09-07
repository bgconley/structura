import {defaultSearchFilterState, modeOptions, familyOptions, reviewStatusOptions, sensitivityOptions,
  relationshipTypeOptions, deadlineTypeOptions, type SearchFilterState} from "./searchFilters";
import type {ViewMode} from "./types";

export type AppRoute =
  | {view: "inbox"; documentId?: string; folderId?: string; query?: string}
  | {view: "viewer"; documentId: string; page: number; returnTo: string}
  | {view: "search"; query: string; filters: SearchFilterState; submitted: boolean}
  | {view: "review"; taskId?: string; documentId?: string}
  | {view: "automation" | "relationships" | "timelines"}
  | {view: "unavailable"; message: string};

const UUID = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i;
const simpleViews = ["automation", "relationships", "timelines"] as const;
const filterKeys = Object.keys(defaultSearchFilterState) as (keyof SearchFilterState)[];

function identifier(value: string | null): string | undefined {
  if (value === null) return undefined;
  if (!UUID.test(value)) throw new Error("This link contains an invalid identifier.");
  return value.toLowerCase();
}

function only(params: URLSearchParams, keys: string[]) {
  if ([...params.keys()].some((key) => !keys.includes(key) || params.getAll(key).length > 1)) {
    throw new Error("This link contains unsupported or repeated options.");
  }
}

function validateFilters(filters: SearchFilterState) {
  const choices = {mode: modeOptions, family: familyOptions, reviewStatus: reviewStatusOptions,
    sensitivity: sensitivityOptions, relationshipType: relationshipTypeOptions, deadlineType: deadlineTypeOptions};
  for (const [key, values] of Object.entries(choices)) {
    if (!(values as readonly string[]).includes(filters[key as keyof typeof choices])) {
      throw new Error("This search link contains an unsupported filter.");
    }
  }
  for (const value of [filters.dateFrom, filters.dateTo]) {
    if (value && (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value))
      || new Date(value).toISOString().slice(0, 10) !== value)) {
      throw new Error("This search link contains an invalid date.");
    }
  }
  if ((filters.dateFrom && filters.dateTo && filters.dateFrom > filters.dateTo)
    || (filters.amountMin && filters.amountMax && Number(filters.amountMin) > Number(filters.amountMax))) {
    throw new Error("This search link contains an inverted range.");
  }
}

export function parseAppRoute(path: string, allowReturn = true): AppRoute {
  try {
    if (!path.startsWith("/") || path.startsWith("//") || path.length > 12_000) {
      throw new Error("This application link is not valid.");
    }
    const url = new URL(path, "https://structura.invalid");
    if (url.origin !== "https://structura.invalid") throw new Error("This application link is not valid.");
    const params = url.searchParams;
    if (url.pathname === "/" || url.pathname === "/inbox") {
      only(params, ["document", "folder", "q"]);
      return {view: "inbox", documentId: identifier(params.get("document")),
        folderId: identifier(params.get("folder")), query: params.get("q") || undefined};
    }
    if (url.pathname === "/search") {
      only(params, ["q", "submitted", ...filterKeys]);
      const filters = {...defaultSearchFilterState};
      for (const key of filterKeys) {
        const value = params.get(key);
        if (value === null) continue;
        if (typeof filters[key] === "boolean") {
          if (value !== "true" && value !== "false") throw new Error("This search link contains an invalid filter.");
          Object.assign(filters, {[key]: value === "true"});
        } else Object.assign(filters, {[key]: value});
      }
      if (!["hybrid", "lexical", "semantic", "visual"].includes(filters.mode)) throw new Error("This search mode is not supported.");
      if (filters.folderId) filters.folderId = identifier(filters.folderId)!;
      validateFilters(filters);
      for (const value of [filters.amountMin, filters.amountMax]) {
        if (value && (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) || !Number.isFinite(Number(value)))) {
          throw new Error("This search link contains an invalid amount.");
        }
      }
      const submitted = params.get("submitted");
      if (submitted && submitted !== "true" && submitted !== "false") throw new Error("This search link is not valid.");
      return {view: "search", query: params.get("q") ?? "", filters,
        submitted: submitted === "true" || (submitted === null && !!params.get("q"))};
    }
    if (url.pathname === "/review") {
      only(params, ["task", "document"]);
      return {view: "review", taskId: identifier(params.get("task")), documentId: identifier(params.get("document"))};
    }
    if (url.pathname.startsWith("/documents/")) {
      only(params, ["page", "returnTo"]);
      const documentId = identifier(url.pathname.slice("/documents/".length));
      const page = params.get("page") ?? "1";
      if (!documentId || !/^[1-9]\d*$/.test(page) || !Number.isSafeInteger(Number(page))) {
        throw new Error("This document link contains an invalid page or identifier.");
      }
      const requestedReturn = params.get("returnTo") ?? "/inbox";
      const destination = allowReturn ? parseAppRoute(requestedReturn, false) : {view: "inbox" as const};
      if (destination.view === "unavailable" || destination.view === "viewer") throw new Error("This return destination is not valid.");
      return {view: "viewer", documentId, page: Number(page), returnTo: allowReturn ? routeUrl(destination) : "/inbox"};
    }
    const view = simpleViews.find((candidate) => url.pathname === `/${candidate}`);
    if (view) { only(params, []); return {view}; }
    return {view: "unavailable", message: "This page is not available. Open Inbox to continue."};
  } catch (error) {
    return {view: "unavailable", message: error instanceof Error ? error.message : "This application link is not valid."};
  }
}

export function routeUrl(route: AppRoute): string {
  const params = new URLSearchParams();
  if (route.view === "inbox") {
    if (route.documentId) params.set("document", route.documentId);
    if (route.folderId) params.set("folder", route.folderId);
    if (route.query) params.set("q", route.query);
  } else if (route.view === "viewer") {
    params.set("page", String(route.page));
    if (route.returnTo !== "/inbox") params.set("returnTo", route.returnTo);
  } else if (route.view === "search") {
    if (route.query) params.set("q", route.query);
    params.set("submitted", String(route.submitted));
    for (const key of filterKeys) if (route.filters[key] !== defaultSearchFilterState[key]) params.set(key, String(route.filters[key]));
  } else if (route.view === "review") {
    if (route.taskId) params.set("task", route.taskId);
    if (route.documentId) params.set("document", route.documentId);
  }
  const path = route.view === "viewer" ? `/documents/${route.documentId}`
    : route.view === "unavailable" ? "/inbox" : `/${route.view}`;
  return path + (params.size ? `?${params}` : "");
}

export function defaultRoute(view: Exclude<ViewMode, "viewer">): AppRoute {
  return view === "search" ? {view, query: "", filters: {...defaultSearchFilterState}, submitted: false} : {view};
}

export function routeLabel(route: AppRoute): string {
  return ({inbox: "Inbox", search: "Search", review: "Review Queue", automation: "Automation",
    relationships: "Relationships", timelines: "Timelines", viewer: "Document", unavailable: "Inbox"})[route.view];
}
