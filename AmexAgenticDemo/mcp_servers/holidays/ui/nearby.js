import { App } from "@modelcontextprotocol/ext-apps";
import { createNearbyController } from "./controller.mjs";

const app = new App({ name: "Nearby Holidays", version: "1.0.0" });
const controller = createNearbyController({
  app, document, geolocation: navigator.geolocation,
});
controller.initialize();
