import { useState } from "react";

import {
  Scale,
  ArrowRight,
  ArrowUpRight,
  Users,
  UserSearch,
  MessageSquare,
  FileText,
  Languages,
  Clock,
  Mic,
  History,
  BookOpen,
  ShieldCheck,
  BadgeCheck,
  Headphones,
} from "lucide-react";

import BrandLogo from "../../components/BrandLogo";

import type { Page } from "../../App";
import { useT } from "../../i18n/context";

type DashboardPageProps = {
  onNavigate: (page: Page) => void;

};

function DashboardPage({ onNavigate }: DashboardPageProps) {
  const { t } = useT();

  /*
   * The courthouse photograph sits at public/courthouse.jpg
   * (see COURTHOUSE_CREDIT.txt for its attribution). If it is
   * ever removed the <img> removes itself and the hero falls
   * back to its gradient wash — the photo is never faked.
   */
  const [heroPhotoFailed, setHeroPhotoFailed] = useState(false);

  return (
    <div className="dashboard-page">

      {/* =====================================================
          NAV — brand, primary routes. The session pill
          (theme, role, sign out) stays fixed at the top-right.
          ===================================================== */}

      <nav className="top-navbar" aria-label={t("nav.main")}>

        <div className="brand">
          <BrandLogo size={44} className="brand-mark" />
          <div>
            <strong className="brand-name">NyayMitra</strong>
            <span className="brand-tagline">{t("nav.brandTagline")}</span>
          </div>
        </div>

        <div className="nav-links">
          <button
            type="button"
            className="nav-link active"
            aria-current="page"
            onClick={() => onNavigate("dashboard")}
          >
            {t("nav.home")}
          </button>

          <button
            type="button"
            className="nav-link"
            onClick={() => onNavigate("cases")}
          >
            {t("nav.myCases")}
          </button>

          <button
            type="button"
            className="nav-link"
            onClick={() => onNavigate("lawyer")}
          >
            {t("nav.findLawyer")}
          </button>

          <button
            type="button"
            className="nav-link"
            onClick={() => onNavigate("chat")}
          >
            {t("nav.chat")}
          </button>
        </div>

        <div />
      </nav>


      {/* =====================================================
          HERO — editorial headline and calls to action on
          the left, the courthouse photograph washed into the
          background on the right, and the welcome/ask card
          overlapping it.
          ===================================================== */}

      <section className="dashboard-hero">

        {!heroPhotoFailed && (
          <img
            className="dashboard-hero-photo"
            src="/nyaymitra-court.png"
            alt=""
            aria-hidden="true"
            onError={() => setHeroPhotoFailed(true)}
          />
        )}

        <div className="dashboard-hero-fade" aria-hidden="true" />

        <div className="dashboard-hero-content">

          <span className="dashboard-eyebrow">
            <Scale size={13} aria-hidden="true" />
            {t("home.eyebrow")}
          </span>

          <h1 className="nm-serif">
            {t("home.title1")}
            <br />
            <span>{t("home.titleAccent")}</span>
          </h1>

          <p>{t("home.copy")}</p>

          <div className="dashboard-hero-ctas">
            <button
              type="button"
              className="dashboard-cta-primary"
              onClick={() => onNavigate("cases")}
            >
              {t("home.ctaExplore")}
              <ArrowRight size={16} aria-hidden="true" />
            </button>

            <button
              type="button"
              className="dashboard-cta-secondary"
              onClick={() => onNavigate("lawyer")}
            >
              <Users size={16} aria-hidden="true" />
              {t("nav.findLawyer")}
            </button>
          </div>

        </div>


      </section>


      {/* =====================================================
          MAIN
          ===================================================== */}

      <main className="dashboard-main">


        {/* =================================================
            LEGAL SERVICES — every service the platform really
            offers, one tile each.
            ================================================= */}

        <section className="dashboard-services">

          <div className="dashboard-section-eyebrow">
            <i aria-hidden="true" />
            {t("home.servicesLabel")}
            <i aria-hidden="true" />
          </div>

          <h2 className="nm-serif">{t("home.servicesHeading")}</h2>


          <div className="dashboard-action-grid">

            <button
              type="button"
              className="dashboard-action-card"
              onClick={() => onNavigate("cases")}
            >
              <span className="dashboard-action-icon purple" aria-hidden="true">
                <Scale size={22} />
              </span>

              <div className="dashboard-action-content">
                <span>{t("home.tile.cases.label")}</span>
                <h3>{t("nav.myCases")}</h3>
                <p>{t("home.tile.cases.desc")}</p>
              </div>

              <ArrowUpRight
                className="dashboard-action-arrow"
                size={19}
                aria-hidden="true"
              />
            </button>


            <button
              type="button"
              className="dashboard-action-card"
              onClick={() => onNavigate("lawyer")}
            >
              <span className="dashboard-action-icon blue" aria-hidden="true">
                <UserSearch size={22} />
              </span>

              <div className="dashboard-action-content">
                <span>{t("home.tile.lawyer.label")}</span>
                <h3>{t("nav.findLawyer")}</h3>
                <p>{t("home.tile.lawyer.desc")}</p>
              </div>

              <ArrowUpRight
                className="dashboard-action-arrow"
                size={19}
                aria-hidden="true"
              />
            </button>


            {/* Opens the shared inbox. Which conversations you
                can actually start is decided in chatApi — for a
                citizen that is lawyers and account staff only. */}
            <button
              type="button"
              className="dashboard-action-card"
              onClick={() => onNavigate("chat")}
            >
              <span className="dashboard-action-icon indigo" aria-hidden="true">
                <MessageSquare size={22} />
              </span>

              <div className="dashboard-action-content">
                <span>{t("home.tile.chat.label")}</span>
                <h3>{t("nav.chat")}</h3>
                <p>{t("home.tile.chat.desc")}</p>
              </div>

              <ArrowUpRight
                className="dashboard-action-arrow"
                size={19}
                aria-hidden="true"
              />
            </button>


            <button
              type="button"
              className="dashboard-action-card"
              onClick={() => onNavigate("orders")}
            >
              <span className="dashboard-action-icon orange" aria-hidden="true">
                <FileText size={22} />
              </span>

              <div className="dashboard-action-content">
                <span>{t("home.tile.orders.label")}</span>
                <h3>{t("home.tile.orders.title")}</h3>
                <p>{t("home.tile.orders.desc")}</p>
              </div>

              <ArrowUpRight
                className="dashboard-action-arrow"
                size={19}
                aria-hidden="true"
              />
            </button>


            <button
              type="button"
              className="dashboard-action-card"
              onClick={() => onNavigate("translation")}
            >
              <span className="dashboard-action-icon green" aria-hidden="true">
                <Languages size={22} />
              </span>

              <div className="dashboard-action-content">
                <span>{t("home.tile.translate.label")}</span>
                <h3>{t("home.tile.translate.title")}</h3>
                <p>{t("home.tile.translate.desc")}</p>
              </div>

              <ArrowUpRight
                className="dashboard-action-arrow"
                size={19}
                aria-hidden="true"
              />
            </button>


            <button
              type="button"
              className="dashboard-action-card"
              onClick={() => onNavigate("delay")}
            >
              <span className="dashboard-action-icon indigo" aria-hidden="true">
                <Clock size={22} />
              </span>

              <div className="dashboard-action-content">
                <span>{t("home.tile.delay.label")}</span>
                <h3>{t("home.tile.delay.title")}</h3>
                <p>{t("home.tile.delay.desc")}</p>
              </div>

              <ArrowUpRight
                className="dashboard-action-arrow"
                size={19}
                aria-hidden="true"
              />
            </button>


            <button
              type="button"
              className="dashboard-action-card"
              onClick={() => onNavigate("jurisAI")}
            >
              <span className="dashboard-action-icon purple" aria-hidden="true">
                <Scale size={22} />
              </span>
              <div className="dashboard-action-content">
                <span>AI LEGAL ASSISTANT</span>
                <h3>Juris AI</h3>
                <p>Ask legal questions or understand a court order in simple language.</p>
              </div>
              <ArrowUpRight
                className="dashboard-action-arrow"
                size={19}
                aria-hidden="true"
              />
            </button>




            <button
              type="button"
              className="dashboard-action-card"
              onClick={() => onNavigate("timeline")}
            >
              <span className="dashboard-action-icon orange" aria-hidden="true">
                <History size={22} />
              </span>

              <div className="dashboard-action-content">
                <span>{t("home.tile.timeline.label")}</span>
                <h3>{t("home.tile.timeline.title")}</h3>
                <p>{t("home.tile.timeline.desc")}</p>
              </div>

              <ArrowUpRight
                className="dashboard-action-arrow"
                size={19}
                aria-hidden="true"
              />
            </button>

          </div>

        </section>


        {/* =====================================================
            HOW NYAYMITRA HELPS — the three promises from the
            reference design.
            ===================================================== */}

        <section className="dashboard-info-section">

          <div className="dashboard-section-eyebrow">
            <i aria-hidden="true" />
            {t("home.helpsLabel")}
            <i aria-hidden="true" />
          </div>

          <h2 className="nm-serif">{t("home.helpsHeading")}</h2>

          <div className="dashboard-info-grid">

            <div className="dashboard-info-card">
              <span className="dashboard-info-icon" aria-hidden="true">
                <BookOpen size={22} />
              </span>
              <div>
                <h3>{t("home.info.understand.title")}</h3>
                <p>{t("home.info.understand.desc")}</p>
              </div>
            </div>


            <div className="dashboard-info-card">
              <span className="dashboard-info-icon" aria-hidden="true">
                <Users size={22} />
              </span>
              <div>
                <h3>{t("home.info.help.title")}</h3>
                <p>{t("home.info.help.desc")}</p>
              </div>
            </div>


            <div className="dashboard-info-card">
              <span className="dashboard-info-icon" aria-hidden="true">
                <Languages size={22} />
              </span>
              <div>
                <h3>{t("home.info.translate.title")}</h3>
                <p>{t("home.info.translate.desc")}</p>
              </div>
            </div>

          </div>

        </section>


        {/* =====================================================
            TRUST BAND — the dark strip from the reference.
            ===================================================== */}

        <section className="dashboard-trust">

          <div className="dashboard-trust-item">
            <ShieldCheck size={22} aria-hidden="true" />
            <div>
              <h3>{t("home.trust.secure.title")}</h3>
              <p>{t("home.trust.secure.desc")}</p>
            </div>
          </div>


          <div className="dashboard-trust-item">
            <BadgeCheck size={22} aria-hidden="true" />
            <div>
              <h3>{t("home.trust.verified.title")}</h3>
              <p>{t("home.trust.verified.desc")}</p>
            </div>
          </div>


          <div className="dashboard-trust-item">
            <Headphones size={22} aria-hidden="true" />
            <div>
              <h3>{t("home.trust.support.title")}</h3>
              <p>{t("home.trust.support.desc")}</p>
            </div>
          </div>

        </section>


        {/* =====================================================
            CLOSING CTA
            ===================================================== */}

        <section className="dashboard-cta">

          <div>
            <span>{t("home.ctaLabel")}</span>

            <h2 className="nm-serif">{t("home.ctaHeading")}</h2>

            <p>{t("home.ctaCopy")}</p>
          </div>

          <button
            type="button"
            onClick={() => onNavigate("cases")}
          >
            {t("home.ctaExplore")}
            <ArrowRight size={15} aria-hidden="true" />
          </button>

        </section>

      </main>

    </div>
  );
}

export default DashboardPage;
