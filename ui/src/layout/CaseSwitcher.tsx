import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { listCases } from "../api/client";
import { ROUTES, casePath } from "../routing";

/**
 * The case column spec 07 §4 draws above the rail — filled at T46, and
 * deliberately empty until now.
 *
 * P2 shipped the shell without it and said why: "a nav bar full of dead links
 * would be a promise the product does not keep". T42 reserved the slot rather
 * than filling it with a switcher that had nothing to switch between, because
 * `GET /v1/cases` did not exist until T43.
 *
 * Two rules it inherits from the route (spec 09 §2.4), both of them the same
 * rule seen from different sides:
 *
 * * **No count.** The response carries no total, and a rail that rendered
 *   "3 cases" would be reporting the size of an authorization-filtered
 *   collection — an existence leak (spec 06 §4 default 4).
 * * **Empty means "none you are in".** Never "none exist", which answers a
 *   question the caller was not permitted to ask.
 */
export function CaseSwitcher() {
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => listCases() });
  const items = cases.data?.items ?? [];

  return (
    <div className="rail__group" data-testid="case-switcher">
      <h2 className="rail__heading">Cases</h2>
      <ul className="rail__list">
        {items.map((entry) => (
          <li key={entry.case_id}>
            <NavLink
              to={casePath(entry.case_id)}
              className={({ isActive }) =>
                `rail__link${isActive ? " rail__link--active" : ""}`
              }
            >
              {entry.title}
            </NavLink>
          </li>
        ))}
        <li>
          <NavLink
            to={ROUTES.cases}
            end
            className={({ isActive }) =>
              `rail__link rail__link--all${isActive ? " rail__link--active" : ""}`
            }
          >
            {items.length === 0 ? "Open a case…" : "All cases"}
          </NavLink>
        </li>
      </ul>
    </div>
  );
}
