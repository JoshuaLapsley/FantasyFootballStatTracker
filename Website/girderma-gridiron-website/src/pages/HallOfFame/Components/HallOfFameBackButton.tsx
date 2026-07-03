import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const styles: { [key: string]: React.CSSProperties } = {
  button: {
    alignSelf: "flex-start",
    margin: "16px",
    padding: "8px 16px",
    background: "#f3f4f6",
    border: "1px solid #e5e7eb",
    borderRadius: "6px",
    cursor: "pointer",
    fontSize: "0.9rem",
    transition: "background 0.15s ease",
  },
};

const HallOfFameBackButton: React.FC = () => {
  const navigate = useNavigate();
  const [hover, setHover] = useState(false);

  return (
    <button
      style={{ ...styles.button, background: hover ? "#e5e7eb" : "#f3f4f6" }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => navigate("/hall-of-fame")}
    >
      ← Back
    </button>
  );
};

export default HallOfFameBackButton;
