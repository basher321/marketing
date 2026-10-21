// cPanel "Setup Node.js App" startup file: runs the Next.js standalone server.
// Passenger sets PORT; standalone keeps its node_modules in the subfolder.
process.env.NODE_ENV = "production";
process.chdir(__dirname + "/standalone");
require("./standalone/server.js");
