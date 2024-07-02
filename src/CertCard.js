import React from 'react';
import { Link } from 'react-router-dom';
import Demo from './Demo';
import { FaGithub } from 'react-icons/fa';
import './ProjectCard.css';

const ProjectCard = ({ title, description, link, githubLink, demoContent }) => {
  return (
    <div className="project-card">
      {demoContent && <Demo content={demoContent} />}
      <div className="project-info">
        <h3 className="project-title">{title}</h3>
        <p className="project-description">{description}</p>
        <div className="spacer"></div>
        <div className="button-wrapper">
          <div className="button-container">
            {link && (<Link to={link} className="project-button">
              <span>Certificate</span>
            </Link>)}
            {githubLink && (
              <button className="project-button github-button" onClick={() => window.open(githubLink, "_blank")}>
                <span><FaGithub /> GitHub</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProjectCard;
