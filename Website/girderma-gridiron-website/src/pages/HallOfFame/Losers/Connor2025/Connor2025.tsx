import React from "react";
import RosterTable from "../../../Components/RosterTable";
import "./Connor2025.css";
import HallOfFameBackButton from "../../Components/HallOfFameBackButton";
import PhotoSlideshow from "../../Components/PhotoSlideShow";

const Connor2025: React.FC = () => {
  return (
    <div className="player-page">
      <HallOfFameBackButton />
      <header className="punishment-header">
        <h1 className="punishment-title">6-12-18-14</h1>
        <p className="punishment-subtitle">Connor's Punishment · 2025</p>
      </header>

      <section className="punishment-story">
        <p>
          People from the league have talked about this punishment for a long time, but this year we finally decided to do it.
        </p>
        <p>
          The punishement went like this. You have 4 numbers, 6,12,18,24. Througout the day (24hr), you have to assign these activities
          to one of the numbers; Beers Drank, Donuts Eaten, Free Throws Made in a Row, KM Traveled. For example, a combination could be
          you eat 6 donuts, travel 12 km, 18 free throws in a row, and 24 beers. Now if you don't complete all these things in a day
          you would have to retry, untill you complete the punishment.
        </p>
        <p>
          Connor set out to do the punishement on July 3rd, 2026. On one of the hottest days of the year. He chose the following; 
          6 Free Throws in a Row, 12 Beers, 18 Donuts, 24 km
        </p>
        
       
      </section>

      <section className="punishment-media">
          <figure className="punishment-figure">
          <img
            src="/ConnorPunishment2025/Kit.jpg"
            alt="Kit"
            className="punishment-image"
          />
          <figcaption>The Kit</figcaption>
        </figure>
      </section>

       <section className="punishment-story">
          <p>
            Connor started out his day with hitting six free throws in a row early in the morning, He Completed his free throws by 6:57AM
          </p>
       </section>

       <section className="punishment-media">
            <figure className="punishment-figure">
              <video controls width="400" className="punishment-video">
                <source src="/ConnorPunishment2025/FailedAttempt.mp4" />
                Your browser doesn't support this video.
              </video>
            <figcaption>Failing On 6th Free Throw</figcaption>
          </figure>
        </section>

        <section className="punishment-media">
            <figure className="punishment-figure">
              <video controls width="400" className="punishment-video">
                <source src="/ConnorPunishment2025/GottenAttempt.mp4" />
                Your browser doesn't support this video.
              </video>
            <figcaption>6 In a row</figcaption>
          </figure>
        </section>

        <section className="punishment-story">
          <p>
            He then started his 24km walk.
          </p>
       </section>

       <section className="punishment-media">
         <figure className="punishment-figure">
          <img
            src="/ConnorPunishment2025/Strategy.jpg"
            alt="Strategy"
            className="punishment-image"
          />
          <figcaption>The Strategy</figcaption>
        </figure>
      </section>

      <section className="punishment-media">
         <figure className="punishment-figure">
          <img
            src="/ConnorPunishment2025/strava.jpg"
            alt="Strava"
            className="punishment-image"
          />
          <figcaption>By Noon he finnished his walk</figcaption>
        </figure>
      </section>


       <section className="punishment-story">
          <p>
            After his walk was over, he went back to his house, and finnished the rest of the donuts and Brews there.
          </p>
       </section>

       <section className="punishment-story">
          <p>
            Here are some additonal images and videos from the Day.
          </p>
       </section>

       <section className="punishment-media">
        <img src="/ConnorPunishment2025/pic1.jpg" alt="picturePicture" className="punishment-image" />
        <img src="/ConnorPunishment2025/pic2.jpg" alt="picturePicture" className="punishment-image" />
        <img src="/ConnorPunishment2025/pic3.jpg" alt="picturePicture" className="punishment-image" />
        <img src="/ConnorPunishment2025/pic4.jpg" alt="picturePicture" className="punishment-image" />
        <video controls width="400" className="punishment-video">
          <source src="/ConnorPunishment2025/EatingDonuts.mp4" />
          Your browser doesn't support this video.
        </video>
      </section>



      <section className="punishment-media">
        <PhotoSlideshow interval={4000} arrowColor="red" aspectRatio="9 / 16">
          <img src="/ConnorPunishment2025/8-11.jpg" alt="8-11" />
          <img src="/ConnorPunishment2025/10-31.jpg" alt="10-31" />
          <img src="/ConnorPunishment2025/12-45pm.jpg" alt="12-45pm" />
          <img src="/ConnorPunishment2025/4-22pm.jpg" alt="4-22pm" />
          <img src="/ConnorPunishment2025/9-55pm.jpg" alt="9-55pm" />
        </PhotoSlideshow>
      </section>

      <section>
        <RosterTable team={"Revy’s Konstruction"} year={"2025"} week={"last"} />
      </section>
    </div>
  );
};

export default Connor2025;