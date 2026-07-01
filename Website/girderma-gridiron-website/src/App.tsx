import React from 'react';
import './App.css';
import NavBar from './shared/NavBar/NavBar';
import { Route, Routes } from "react-router-dom";
import HomePage from './pages/HomePage/HomePage';

import { registerLicense } from "@syncfusion/ej2-base";
import LeagueHistory from './pages/LeagueHistory/LeagueHistory';


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
      </Routes>
    </div>
  );
};

export default App;
