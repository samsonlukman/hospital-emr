import "./BrandBar.css";

export function BrandBar() {
  return (
    <div className="abikan-brand-bar">
      <img
        className="abikan-brand-bar__logo"
        src={`${import.meta.env.BASE_URL}abikan-logo.png`}
        alt="Hospital EMR"
      />
      <p className="abikan-brand-bar__name">Hospital EMR</p>
    </div>
  );
}
