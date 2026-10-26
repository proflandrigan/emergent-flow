/* AUTO-GENERATED from tour.schema.json by `npm run gen:types`. Do not edit. */

export type Author = string;
export type Conclusion = string;
export type Id = string;
/**
 * @maxItems 50
 */
export type Focus = string[];
export type Note = string;
export type Reach = ("up" | "down" | "both") | null;
export type Route = [string, string] | null;
/**
 * @maxItems 20
 */
export type Unknowns = string[];
/**
 * @minItems 1
 * @maxItems 100
 */
export type Steps = TourStep[];
export type Title = string;

/**
 * An ordered guided walkthrough of the session graph.
 */
export interface Tour {
  author: Author;
  conclusion: Conclusion;
  id?: Id;
  steps: Steps;
  title: Title;
}
/**
 * One step of a tour: a focus set (with optional reach) or a route, plus a note.
 */
export interface TourStep {
  focus?: Focus;
  note: Note;
  reach?: Reach;
  route?: Route;
  unknowns?: Unknowns;
}
