import React from 'react';
import './App.css';
import NavBar from './shared/NavBar/NavBar';
import { Route, Routes } from "react-router-dom";
import HomePage from './pages/HomePage/HomePage';

import { registerLicense } from "@syncfusion/ej2-base";
import LeagueHistory from './pages/LeagueHistory/LeagueHistory';
import Zach2023 from './pages/HallOfFame/Winners/Zach2023/Zach2023';
import Connor2024 from './pages/HallOfFame/Winners/Connor2024/Connor2024';
import Zach2025 from './pages/HallOfFame/Winners/Zach2025/Zach2025';
import Connor2023 from './pages/HallOfFame/Losers/Connor2023/Connor2023';
import Jackson2024 from './pages/HallOfFame/Losers/Jackson2024/Jackson2024';
import HallOfFame from './pages/HallOfFame/HallOfFame';
import Connor2025 from './pages/HallOfFame/Losers/Connor2025/Connor2025';


const App: React.FC = () => {

  registerLicense(
    "Ngo9BigBOggjHTQxAR8/V1JHaF1cXGZCf1FpRmJGdld5fUVHYVZUTXxaS00DNHVRdkdlWXhecXVQR2BeU01/XUpWYEo="
  );

  return (
    <div className="App">
      <NavBar />
      <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/league-history" element={<LeagueHistory />} />
          <Route path="/hall-of-fame" element={<HallOfFame />} />

          {/* Winners */}
          <Route path="/hall-of-fame/For Pitts and Giggles/2023" element={<Zach2023 />} />
          <Route path="/hall-of-fame/Revy’s Konstruction/2024" element={<Connor2024 />} />
          <Route path="/hall-of-fame/Go With The Flow/2025" element={<Zach2025 />} />

          {/* Losers */}
          <Route path="/hall-of-fame/Revy’s Konstruction/2023" element={<Connor2023 />} />
          <Route path="/hall-of-fame/Sparty's Sigmas/2024" element={<Jackson2024 />} />
          <Route path="/hall-of-fame/Revy’s Konstruction/2025" element={<Connor2025 />} />
      </Routes>
    </div>
  );
};

export default App;
