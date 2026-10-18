/* =========================================================
   INITIALS

   Small shared helper: every avatar in the dashboards is
   drawn from the name rather than fetched, so the same two
   letter rule has to apply everywhere or rows stop lining
   up. Lives in its own module because RoleSectionView both
   uses it and is imported by screens that render row
   avatars, and react-refresh will not let a component file
   export a plain function alongside its default component.
   ========================================================= */

export function initialsOf(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}
